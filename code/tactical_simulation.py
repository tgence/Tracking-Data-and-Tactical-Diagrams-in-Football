# tactical_simulation.py
"""
Tactical simulation based on user-drawn arrows.

Associates arrows with players and action types (pass/run/dribble), then
computes simulated player and ball positions over a chosen interval.
"""

import numpy as np
import math
from PyQt6.QtCore import QPointF
from config import *

class TacticalSimulationManager:
    """Manage tactical associations and compute simulated trajectories.

    Parameters
    ----------
    annotation_manager : AnnotationManager object
        Manager exposing user-drawn arrows and selection.
    pitch_widget : PitchWidget object
        Pitch widget with `scene` used for drawing.
    home_ids, away_ids : list[str]
        Player IDs for each team.
    home_colors, away_colors : dict
        Mapping `player_id -> (main_hex, secondary_hex, number_hex)`.
    """
    
    def __init__(self, annotation_manager, pitch_widget, home_ids, away_ids, home_colors, away_colors):
        self.annotation_manager = annotation_manager
        self.pitch_widget = pitch_widget
        self.home_ids = home_ids
        self.away_ids = away_ids
        self.home_colors = home_colors
        self.away_colors = away_colors
        
        # Tactical data
        self.tactical_arrows = []  # arrows with associated players
        self.ball_possession_chain = []  # pass chain
        self.player_associations = {}  # {arrow_id: player_id}
        self.pass_receivers = {}  # {arrow_id: receiver_player_id} for passes
        
        # Simulated trajectories
        self.simulated_player_positions = {}  # {player_id: [(x, y, frame), ...]}
        self.simulated_ball_positions = []  # [(x, y, frame), ...]
        
    def associate_arrow_with_player(self, arrow, player_id, current_frame, xy_objects):
        """Associate a drawn arrow with a player at a given frame.

        Parameters
        ----------
        arrow : QGraphicsItemGroup
            Arrow item to associate.
        player_id : str
            Player ID to associate with this arrow.
        current_frame : int
            Global frame when the association is made.
        xy_objects : dict
            Positions object (not used directly here, but may be used downstream).

        Returns
        -------
        str
            "waiting_for_receiver" for passes, otherwise "associated".
        """
        arrow_id = id(arrow)
        self.player_associations[arrow_id] = player_id
        
        # Create the tactical_arrow object
        tactical_arrow = {
            'arrow': arrow,
            'arrow_id': arrow_id,
            'player_id': player_id,
            'action_type': self.get_action_type(arrow),
            'start_pos': arrow.arrow_points[0],
            'end_pos': arrow.arrow_points[-1],
            'length': self.calculate_arrow_length(arrow.arrow_points),
            'associated_frame': current_frame
        }
        
        self.tactical_arrows.append(tactical_arrow)
        
        # If it's a pass (solid), ask for receiver
        if tactical_arrow['action_type'] == 'pass':
            return "waiting_for_receiver"
        
        return "associated"
    
    def set_pass_receiver(self, receiver_player_id):
        """Define the pass receiver for the most recent unassigned pass arrow.

        Parameters
        ----------
        receiver_player_id : str
            Player ID designated as receiver.

        Returns
        -------
        bool
            True if a pending pass was updated, False otherwise.
        """
        # Find the most recent pass without a receiver
        for tactical_arrow in reversed(self.tactical_arrows):
            if (tactical_arrow['action_type'] == 'pass' and 
                'receiver_id' not in tactical_arrow):
                
                arrow_id = tactical_arrow['arrow_id']
                self.pass_receivers[arrow_id] = receiver_player_id
                tactical_arrow['receiver_id'] = receiver_player_id
                
                # Add to possession chain
                self.ball_possession_chain.append({
                    'from_player': tactical_arrow['player_id'],
                    'to_player': receiver_player_id,
                    'arrow_id': arrow_id
                })
                
                return True
        return False
    
    def get_action_type(self, arrow):
        """Infer action type from arrow style.

        Parameters
        ----------
        arrow : QGraphicsItemGroup
            Arrow with `arrow_style` attribute or child pen styles.

        Returns
        -------
        {'pass','run','dribble'}
            Inferred action type: solid=pass, dotted=run, zigzag=dribble.
        """
        if hasattr(arrow, 'arrow_style'):
            style = arrow.arrow_style
            if style == "dotted":
                return 'run'  # Dotted = run
            elif style == "zigzag":
                return 'dribble'  # Zigzag = dribble
            else:
                return 'pass'  # Solid = pass
        
        # Fallback: inspect child items if style attribute is missing
        if hasattr(arrow, 'childItems') and arrow.childItems():
            for item in arrow.childItems():
                if hasattr(item, 'pen'):
                    pen = item.pen()
                    if pen.style() == Qt.PenStyle.DashLine:
                        return 'run'
                    break
        
        # Default to pass (solid)
        return 'pass'
    
    def calculate_arrow_length(self, points):
        """Compute the total Euclidean length of an arrow polyline.

        Parameters
        ----------
        points : list[QPointF]
            Sequence of points forming the polyline.

        Returns
        -------
        float
            Polyline length.
        """
        if len(points) < 2:
            return 0
        
        total_length = 0
        for i in range(len(points) - 1):
            dx = points[i+1].x() - points[i].x()
            dy = points[i+1].y() - points[i].y()
            total_length += math.sqrt(dx*dx + dy*dy)
        
        return total_length
    
    def calculate_simulated_trajectories(self, interval_seconds, current_frame, xy_objects, n_frames, get_frame_data_func):
        """Compute positions for players and ball over the simulation interval.

        Parameters
        ----------
        interval_seconds : float
            Duration of the simulation window in seconds.
        current_frame : int
            Global frame where the simulation starts.
        xy_objects : dict
            Positions per half/side and the ball.
        n_frames : int
            Total number of frames.
        get_frame_data_func : callable
            Function mapping global frame -> (half, half_idx, label).
        """
        self.simulated_player_positions.clear()
        self.simulated_ball_positions.clear()
        
        if not self.tactical_arrows:
            return
        
        total_frames = int(interval_seconds * FPS)
        ball_current_pos = None
        ball_holder = None
        
        # Get initial ball position
        half, idx, _ = get_frame_data_func(current_frame)
        try:
            ball_xy = xy_objects[half]["Ball"].xy[idx]
            if len(ball_xy) >= 2 and not np.isnan(ball_xy[0]):
                ball_current_pos = QPointF(ball_xy[0], ball_xy[1])
                # Determine who has the ball initially
                ball_holder = self._find_closest_player_to_ball(ball_current_pos, current_frame, xy_objects, get_frame_data_func)
        except (IndexError, KeyError):
            pass
        
        # Sort actions by order and timing
        passes = [ta for ta in self.tactical_arrows if ta['action_type'] == 'pass']
        other_actions = [ta for ta in self.tactical_arrows if ta['action_type'] in ['run', 'dribble']]
        
        # Calculate trajectories for each frame
        for frame_offset in range(total_frames):
            current_sim_frame = current_frame + frame_offset
            progress = frame_offset / max(1, total_frames - 1)
            
            # Process player actions according to calculated speed
            for tactical_arrow in self.tactical_arrows:
                player_id = tactical_arrow['player_id']
                action_type = tactical_arrow['action_type']
                # Calculate player position according to arrow and required speed over full interval
                player_pos = self._calculate_player_position_with_speed(
                    tactical_arrow, progress, interval_seconds, current_frame, xy_objects, get_frame_data_func
                )
                
                if player_id not in self.simulated_player_positions:
                    self.simulated_player_positions[player_id] = []
                
                self.simulated_player_positions[player_id].append((
                    player_pos.x(), player_pos.y(), current_sim_frame
                ))
            
            # Calculate ball position with pass speed
            if ball_current_pos and ball_holder:
                ball_pos = self._calculate_ball_position_with_speed(
                    ball_current_pos, ball_holder, passes, progress, interval_seconds, 
                    current_frame, xy_objects, get_frame_data_func
                )
                self.simulated_ball_positions.append((
                    ball_pos.x(), ball_pos.y(), current_sim_frame
                ))

    
    
    def _calculate_player_position_with_speed(self, tactical_arrow, progress, interval_seconds, current_frame, xy_objects, get_frame_data_func):
        """Position a player along the arrow, capped by plausible action speed.

        Parameters
        ----------
        tactical_arrow : dict
            Metadata for an associated arrow (start/end, type, length).
        progress : float
            Normalized progress in [0, 1] within the simulation window.
        interval_seconds : float
            Duration of the simulation window (seconds).
        current_frame : int
            Global frame when the simulation starts.
        xy_objects : dict
            Positions structure (unused here).
        get_frame_data_func : callable
            Global frame -> (half, half_idx, label).

        Returns
        -------
        PyQt5.QtCore.QPointF
            Interpolated player position.
        """
        start_pos = tactical_arrow['start_pos']
        end_pos = tactical_arrow['end_pos']
        arrow_length = tactical_arrow['length']
        
        # Calculate required speed (meters per second)
        required_speed = arrow_length / interval_seconds
        
        # Realistic maximum speed according to action type
        max_speeds = {
            'run': 8.0,      # 8 m/s fast run
            'dribble': 4.0,  # 4 m/s dribbling
            'pass': 0.0      # Passes have no player speed limit
        }
        
        action_type = tactical_arrow['action_type']
        
        if action_type in max_speeds and max_speeds[action_type] > 0:
            # Limit speed if necessary
            max_allowed_speed = max_speeds[action_type]
            if required_speed > max_allowed_speed:
                # Player doesn't reach the end in the allotted time
                # He covers the distance he can at max speed
                distance_covered = max_allowed_speed * interval_seconds * progress
                total_distance = arrow_length
                actual_progress = min(distance_covered / total_distance, 1.0)
            else:
                actual_progress = progress
        else:
            # For passes, use normal progress
            actual_progress = progress
        
        # Interpolation along the arrow
        x = start_pos.x() + actual_progress * (end_pos.x() - start_pos.x())
        y = start_pos.y() + actual_progress * (end_pos.y() - start_pos.y())
        
        return QPointF(x, y)
    
    def _calculate_ball_position_with_speed(self, initial_ball_pos, initial_holder, passes, progress, interval_seconds, current_frame, xy_objects, get_frame_data_func):
        """Compute ball position given pass speed and receiver path.

        Parameters
        ----------
        initial_ball_pos : QPointF
        initial_holder : str
            Initial ball holder player ID.
        passes : list[dict]
            Tactical arrows marked as passes.
        progress : float
            Progress in [0, 1] of the overall simulation interval.
        interval_seconds : float
        current_frame : int
        xy_objects : dict
        get_frame_data_func : callable

        Returns
        -------
        PyQt5.QtCore.QPointF
            Ball position at current progress.
        """
        if not passes:
            # No pass, ball follows initial carrier
            if initial_holder in self.simulated_player_positions:
                positions = self.simulated_player_positions[initial_holder]
                if positions:
                    latest_pos = positions[-1]
                    return QPointF(latest_pos[0], latest_pos[1])
            return initial_ball_pos
        
        # Process passes in sequence according to their timing
        current_pass = None
        pass_start_time = 0.0
        
                    # For simplicity, process the first pass

        first_pass = passes[0]
        
        if 'receiver_id' in first_pass:
            pass_length = first_pass['length']
            
            # Realistic pass speed (15-25 m/s for a normal pass)
            pass_speed = min(25.0, max(15.0, pass_length / 2.0))  # Adapted to distance
            pass_duration = pass_length / pass_speed
            
            # Convert to proportion of total time
            pass_duration_ratio = min(pass_duration / interval_seconds, 0.8)  # Max 80% of time
            
            if progress <= pass_duration_ratio:
                # Pass in progress - interpolate between passer and receiver
                pass_progress = progress / pass_duration_ratio
                
                # Passer position
                passer_pos = self._calculate_player_position_with_speed(
                    first_pass, progress, interval_seconds, current_frame, xy_objects, get_frame_data_func
                )
                
                # Receiver position
                receiver_pos = self._get_player_position_at_progress(
                    first_pass['receiver_id'], progress, interval_seconds, current_frame, xy_objects, get_frame_data_func
                )
                
                # Interpolate ball with slightly curved trajectory
                x = passer_pos.x() + pass_progress * (receiver_pos.x() - passer_pos.x())
                y = passer_pos.y() + pass_progress * (receiver_pos.y() - passer_pos.y())
                
                return QPointF(x, y)
            else:
                # Pass completed - ball follows receiver
                receiver_pos = self._get_player_position_at_progress(
                    first_pass['receiver_id'], progress, interval_seconds, current_frame, xy_objects, get_frame_data_func
                )
                return receiver_pos
        
        return initial_ball_pos
    
    def _get_player_position_at_progress(self, player_id, progress, interval_seconds, current_frame, xy_objects, get_frame_data_func):
        """Return simulated or real player position at a given progress ratio.

        Returns
        -------
        PyQt5.QtCore.QPointF
            Player position.
        """
        # First check if there's a simulated position
        if player_id in self.simulated_player_positions:
            positions = self.simulated_player_positions[player_id]
            if positions:
                # Take position corresponding to progress
                target_index = int(progress * (len(positions) - 1))
                target_index = min(target_index, len(positions) - 1)
                latest_pos = positions[target_index]
                return QPointF(latest_pos[0], latest_pos[1])
        
        # Otherwise, use real position
        frame_to_check = current_frame + int(progress * interval_seconds * FPS)
        return self._get_real_player_position(player_id, frame_to_check, xy_objects, get_frame_data_func)
    
    def _get_real_player_position(self, player_id, frame, xy_objects, get_frame_data_func):
        """Return real player position at a given global frame index.

        Returns
        -------
        PyQt5.QtCore.QPointF
            Player position; (0, 0) if unavailable.
        """
        half, idx, _ = get_frame_data_func(frame)
        
        # Determine player's team
        side = "Home" if player_id in self.home_ids else "Away"
        ids = self.home_ids if side == "Home" else self.away_ids
        
        try:
            player_index = ids.index(player_id)
            xy = xy_objects[half][side].xy[idx]
            
            if 2*player_index+1 < len(xy):
                x, y = xy[2*player_index], xy[2*player_index+1]
                if not np.isnan(x) and not np.isnan(y):
                    return QPointF(x, y)
        except (ValueError, IndexError, KeyError):
            pass
        
        return QPointF(0, 0)  # Default position
    
    def _find_closest_player_to_ball(self, ball_pos, frame, xy_objects, get_frame_data_func):
        """Find the player closest to the ball at a frame.

        Returns
        -------
        str | None
            Player ID or None if not found.
        """
        min_distance = float('inf')
        closest_player = None
        
        for side, ids in [("Home", self.home_ids), ("Away", self.away_ids)]:
            for player_id in ids:
                player_pos = self._get_real_player_position(player_id, frame, xy_objects, get_frame_data_func)
                distance = math.sqrt(
                    (ball_pos.x() - player_pos.x())**2 + 
                    (ball_pos.y() - player_pos.y())**2
                )
                
                if distance < min_distance:
                    min_distance = distance
                    closest_player = player_id
        
        return closest_player
    
    def find_player_at_position(self, click_pos, current_frame, xy_objects, get_frame_data_func, max_distance=PLAYER_OUTER_RADIUS_BASE):
        """Find the nearest player to an arbitrary click within a threshold.

        Parameters
        ----------
        click_pos : PyQt5.QtCore.QPointF
        current_frame : int
        xy_objects : dict
        get_frame_data_func : callable
        max_distance : float, default config.PLAYER_OUTER_RADIUS_BASE

        Returns
        -------
        str | None
            Closest player ID within threshold, else None.
        """
        min_distance = float('inf')
        closest_player = None
        
        for side, ids in [("Home", self.home_ids), ("Away", self.away_ids)]:
            for player_id in ids:
                player_pos = self._get_real_player_position(player_id, current_frame, xy_objects, get_frame_data_func)
                distance = math.sqrt(
                    (click_pos.x() - player_pos.x())**2 + 
                    (click_pos.y() - player_pos.y())**2
                )
                
                if distance < min_distance and distance <= max_distance:
                    min_distance = distance
                    closest_player = player_id
        
        return closest_player
    
    def clear_tactical_data(self):
        """Reset tactical associations and all simulated positions."""
        self.tactical_arrows.clear()
        self.ball_possession_chain.clear()
        self.player_associations.clear()
        self.pass_receivers.clear()
        self.simulated_player_positions.clear()
        self.simulated_ball_positions.clear()
    
    def get_simulated_trajectories(self):
        """Return simulated player and ball trajectories for rendering.

        Returns
        -------
        dict
            {'players': dict, 'ball': list}
        """
        return {
            'players': self.simulated_player_positions,
            'ball': self.simulated_ball_positions
        }
    
    def get_non_associated_arrows(self):
        """Return arrows that are not associated with any player.

        Returns
        -------
        list
            Arrow items not in the associated set.
        """
        associated_arrow_ids = {ta['arrow_id'] for ta in self.tactical_arrows}
        all_arrows = self.annotation_manager.arrows
        
        non_associated = []
        for arrow in all_arrows:
            if id(arrow) not in associated_arrow_ids:
                non_associated.append(arrow)
        
        return non_associated
    
    def get_associated_arrows(self):
        """Return a copy of associated arrows with their tactical metadata.

        Returns
        -------
        list[dict]
            Shallow copy of internal tactical arrows list.
        """
        return self.tactical_arrows.copy()
    
    def remove_arrow_association(self, arrow):
        """Remove association for the specified arrow and clean related state.

        Parameters
        ----------
        arrow : QGraphicsItemGroup
            Arrow item whose association must be removed.
        """
        arrow_id = id(arrow)
        
        # Remove from tactical_arrows
        self.tactical_arrows = [ta for ta in self.tactical_arrows if ta['arrow_id'] != arrow_id]
        
        # Remove associations
        if arrow_id in self.player_associations:
            del self.player_associations[arrow_id]
        
        # Remove from pass receivers
        if arrow_id in self.pass_receivers:
            del self.pass_receivers[arrow_id]
        
        # Remove from possession chain
        self.ball_possession_chain = [
            link for link in self.ball_possession_chain 
            if link['arrow_id'] != arrow_id
        ]