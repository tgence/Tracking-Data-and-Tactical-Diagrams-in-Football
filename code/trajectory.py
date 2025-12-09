# trajectory.py
"""
Trajectory computation and rendering for players and ball.

`TrajectoryManager` computes/draws future real trajectories and simulated ones,
with temporal fading so upcoming segments are more visible than distant ones.
"""

from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt
from collections import deque
import numpy as np
from config import *

class TrajectoryManager:
    """Manage drawing of future and simulated trajectories for players/ball.

    Parameters
    ----------
    pitch_widget : PitchWidget object
        Widget providing access to `scene` and helpers to add items.
    home_colors, away_colors : dict
        Mapping `player_id -> (main_hex, secondary_hex, number_hex)`.
    """

    def __init__(self, pitch_widget, home_colors, away_colors):
        self.pitch_widget = pitch_widget
        self.player_trails = {}
        self.future_trajectories = {}
        self.cached_frame = None  # Cache to avoid recomputing
        self.cached_interval = None
        self.home_colors = home_colors
        self.away_colors = away_colors
        self.simulated_trajectories = {}  # Tactical simulated trajectories
        
    def clear_trails(self):
        """Clear cached and drawn trajectories from the scene."""
        self.player_trails.clear()
        self.future_trajectories.clear()
        self.simulated_trajectories.clear()
        self.cached_frame = None
        self.cached_interval = None
        
    def calculate_future_trajectories(self, current_frame, interval_seconds, xy_objects, 
                                    home_ids, away_ids, n_frames, get_frame_data_func):
        """Compute future positions for players/ball for the given interval.

        Parameters
        ----------
        current_frame : int
            Global frame used as the start of the preview horizon.
        interval_seconds : float
            Length of the horizon in seconds.
        xy_objects : dict
            Positions per half/side and for the ball.
        home_ids, away_ids : list[str]
            Player IDs for each side.
        n_frames : int
            Total number of frames in the dataset.
        get_frame_data_func : callable
            Function mapping global frame -> (half, half_idx, label).

        Notes
        -----
        Uses a sampling step (``CONFIG.TRAJECTORY_SAMPLE_RATE``) and caches
        results for the same (frame, interval) pair to avoid recomputation.
        """
        # Optimization: cache to avoid recomputing for the same (frame, interval)
        if (self.cached_frame == current_frame and 
            self.cached_interval == interval_seconds and 
            self.future_trajectories):
            return
        
        future_frames = int(interval_seconds * FPS)
        end_frame = min(current_frame + future_frames, n_frames - 1)
        
        self.future_trajectories = {
            'players': {'Home': {}, 'Away': {}},
            'ball': []
        }
        
        # Optimization: sample to reduce the number of points drawn
        sample_step = TRAJECTORY_SAMPLE_RATE
        
        for frame in range(current_frame, end_frame + 1, sample_step):
            half, idx, _ = get_frame_data_func(frame)
            progress = (frame - current_frame) / max(1, future_frames)
            
            # Players
            for side, ids in [("Home", home_ids), ("Away", away_ids)]:
                try:
                    xy = xy_objects[half][side].xy[idx]
                    for i, pid in enumerate(ids):
                        if 2*i+1 < len(xy):  # Bounds check
                            x, y = xy[2*i], xy[2*i+1]
                            if not np.isnan(x) and not np.isnan(y):
                                if pid not in self.future_trajectories['players'][side]:
                                    self.future_trajectories['players'][side][pid] = []
                                # Also store the frame for comparison against current_frame
                                self.future_trajectories['players'][side][pid].append((x, y, progress, frame))
                except (IndexError, KeyError):
                    continue
            
            # Ball
            try:
                ball_xy = xy_objects[half]["Ball"].xy[idx]
                if len(ball_xy) >= 2 and not np.isnan(ball_xy[0]):
                    # Also store the frame for the ball
                    self.future_trajectories['ball'].append((ball_xy[0], ball_xy[1], progress, frame))
            except (IndexError, KeyError):
                continue
        
        # Update cache
        self.cached_frame = current_frame
        self.cached_interval = interval_seconds
    
    def draw_future_trajectories(self, show_players=True, show_ball=True, current_frame=None, 
                               loop_start=None, loop_end=None, interval_seconds=10.0, ball_color=BALL_COLOR):
        """Draw future trajectories with progressive fading.

        Parameters
        ----------
        show_players, show_ball : bool, default True
            Toggles for rendering player and ball trajectories.
        current_frame : int or None
            If provided, only draw future segments relative to this frame.
        loop_start, loop_end : int or None
            Loop bounds (unused here; kept for API similarity).
        interval_seconds : float, default 10.0
            Horizon used to compute per-segment fade.
        ball_color : str
            Hex color for the ball trajectory.
        """
        
        # Compute fade frame counts based on the chosen interval
        fade_frames_players = int(interval_seconds * FPS)  # full interval for players
        fade_frames_ball = int(interval_seconds * FPS)     # same for the ball
        
        if show_players:
            for side, players in self.future_trajectories.get('players', {}).items():
                for pid, positions in players.items():
                    base_color = self.home_colors[pid][0] if side == "Home" else self.away_colors[pid][0]
                    if len(positions) > 1:
                        sampled_positions = positions[::2]
                        
                        for i in range(len(sampled_positions) - 1):
                            x1, y1, p1, frame1 = sampled_positions[i]
                            x2, y2, p2, frame2 = sampled_positions[i+1]
                            
                            # Draw only future segments unless fading is disabled
                            if CONFIG and getattr(CONFIG, '__class__', None):
                                fading_enabled = True if 'TRAJECTORY_FADING' not in globals() else TRAJECTORY_FADING
                            else:
                                fading_enabled = True
                            if fading_enabled:
                                if current_frame is not None and current_frame > frame1:
                                    continue
                            
                            # Inverted alpha logic
                            color = QColor(base_color)
                            if 'TRAJECTORY_FADING' in globals() and not TRAJECTORY_FADING:
                                final_alpha = 1.0
                            else:
                                if current_frame is not None:
                                    frames_until_segment = frame1 - current_frame
                                    # Closer segments are more opaque (~1.0)
                                    # Farther segments are more transparent (~0.2)
                                    distance_factor = frames_until_segment / fade_frames_players
                                    # Inverted mapping: near -> opaque, far -> transparent
                                    final_alpha = max(0.2, 1.0 - distance_factor * 0.8)
                                else:
                                    final_alpha = 0.8
                            
                            color.setAlphaF(final_alpha)
                            
                            # Very thin dashed line
                            pen = QPen(color, CONFIG.TRAJECTORY_PLAYER_LINE_WIDTH)
                            pen.setStyle(Qt.PenStyle.CustomDashLine)
                            pen.setDashPattern([1, 4])
                            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                            
                            line = self.pitch_widget.scene.addLine(x1, y1, x2, y2, pen)
                            line.setZValue(8)
                            self.pitch_widget.dynamic_items.append(line)
        
        if show_ball:
            ball_positions = self.future_trajectories.get('ball', [])
            if len(ball_positions) > 1:
                sampled_ball_positions = ball_positions[::2]
                
                for i in range(len(sampled_ball_positions) - 1):
                    x1, y1, p1, frame1 = sampled_ball_positions[i]
                    x2, y2, p2, frame2 = sampled_ball_positions[i+1]
                    
                    # Only draw future segments unless fading is disabled
                    if 'TRAJECTORY_FADING' in globals() and TRAJECTORY_FADING:
                        if current_frame is not None and current_frame > frame1:
                            continue
                    
                    # Same inverted alpha logic for the ball
                    color = QColor(ball_color)
                    if 'TRAJECTORY_FADING' in globals() and not TRAJECTORY_FADING:
                        final_alpha = 1.0
                    else:
                        if current_frame is not None:
                            frames_until_segment = frame1 - current_frame
                            # Closer segments are more opaque (~1.0)
                            # Farther segments are more transparent (~0.3)
                            distance_factor = frames_until_segment / fade_frames_ball
                            # Inverted mapping: near -> opaque, far -> transparent
                            final_alpha = max(0.3, 1.0 - distance_factor * 0.7)
                        else:
                            final_alpha = 0.9
                    
                    color.setAlphaF(final_alpha)
                    
                    pen = QPen(color, CONFIG.TRAJECTORY_BALL_LINE_WIDTH)
                    pen.setStyle(TRAJECTORY_STYLE)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    
                    line = self.pitch_widget.scene.addLine(x1, y1, x2, y2, pen)
                    line.setZValue(95)
                    self.pitch_widget.dynamic_items.append(line)
                
                # Final position - always fully opaque and visible until reached
                if ball_positions:
                    final_x, final_y, final_progress, final_frame = ball_positions[-1]
                    
                    # Draw while the final position hasn't been reached yet
                    if current_frame is None or current_frame < final_frame:
                        # Slightly larger radius and full circle
                        final_radius = CONFIG.BALL_RADIUS * 1.2  # ~20% bigger than normal ball
                        pen_color = QColor(ball_color)
                        pen_color.setAlphaF(1.0)  # always fully opaque
                        
                        # Solid ring (not dashed) with a thin outline
                        final_ball = self.pitch_widget.scene.addEllipse(
                            final_x - final_radius, final_y - final_radius,
                            final_radius * 2, final_radius * 2,
                            QPen(pen_color, 0.4, Qt.PenStyle.SolidLine),
                            QBrush(Qt.BrushStyle.NoBrush)
                        )
                        final_ball.setZValue(96)
                        self.pitch_widget.dynamic_items.append(final_ball)

    def draw_simulated_trajectories(self, simulated_data, current_frame, loop_start, loop_end, ball_color=BALL_COLOR):
        """Draw simulated trajectories on top of the real ones.

        Parameters
        ----------
        simulated_data : dict
            Output from TacticalSimulationManager.get_simulated_trajectories().
        current_frame : int
            Current global frame in the playback.
        loop_start, loop_end : int
            Loop bounds for opacity computation.
        ball_color : str
            Hex color for simulated ball path.
        """
        if not simulated_data:
            return
        
        # Draw simulated player trajectories
        players_data = simulated_data.get('players', {})
        for player_id, positions in players_data.items():
            if len(positions) > 1:
                # Determine team for color
                side = "Home" if player_id in self.home_colors else "Away"
                base_color = self.home_colors.get(player_id, ["#FF0000"])[0] if side == "Home" else self.away_colors.get(player_id, ["#0000FF"])[0]
                
                # Draw segments with progressive fading
                for i in range(len(positions) - 1):
                    x1, y1, frame1 = positions[i]
                    x2, y2, frame2 = positions[i + 1]
                    
                    # Only draw future segments unless fading is disabled
                    if 'TRAJECTORY_FADING' in globals() and TRAJECTORY_FADING:
                        if current_frame is not None and current_frame > frame1:
                            continue
                    
                    # Compute opacity based on temporal distance
                    color = QColor(base_color)
                    if 'TRAJECTORY_FADING' in globals() and not TRAJECTORY_FADING:
                        final_alpha = 1.0
                    else:
                        if current_frame is not None:
                            frames_until_segment = frame1 - current_frame
                            total_frames = loop_end - loop_start
                            
                            if total_frames > 0:
                                distance_factor = frames_until_segment / total_frames
                                # Closer -> more opaque
                                final_alpha = max(0.4, 1.0 - distance_factor * 0.6)
                            else:
                                final_alpha = 0.9
                        else:
                            final_alpha = 0.9
                    
                    color.setAlphaF(final_alpha)
                    
                    # Thicker solid line for simulated path
                    pen = QPen(color, CONFIG.TRAJECTORY_PLAYER_LINE_WIDTH * 2)
                    pen.setStyle(Qt.PenStyle.SolidLine)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    
                    line = self.pitch_widget.scene.addLine(x1, y1, x2, y2, pen)
                    line.setZValue(15)  # Above real trajectories
                    self.pitch_widget.dynamic_items.append(line)
        
        # Draw simulated ball trajectory
        ball_positions = simulated_data.get('ball', [])
        if len(ball_positions) > 1:
            for i in range(len(ball_positions) - 1):
                x1, y1, frame1 = ball_positions[i]
                x2, y2, frame2 = ball_positions[i + 1]
                
                # Only draw future segments unless fading is disabled
                if 'TRAJECTORY_FADING' in globals() and TRAJECTORY_FADING:
                    if current_frame is not None and current_frame > frame1:
                        continue
                
                # Compute opacity for the ball
                color = QColor(BALL_COLOR)
                if 'TRAJECTORY_FADING' in globals() and not TRAJECTORY_FADING:
                    final_alpha = 1.0
                else:
                    if current_frame is not None:
                        frames_until_segment = frame1 - current_frame
                        total_frames = loop_end - loop_start
                        
                        if total_frames > 0:
                            distance_factor = frames_until_segment / total_frames
                            # Closer -> more opaque
                            final_alpha = max(0.5, 1.0 - distance_factor * 0.5)
                        else:
                            final_alpha = 1.0
                    else:
                        final_alpha = 1.0
                
                color.setAlphaF(final_alpha)
                
                # Thicker line for the simulated ball
                pen = QPen(color, CONFIG.TRAJECTORY_BALL_LINE_WIDTH * 2)
                pen.setStyle(Qt.PenStyle.SolidLine)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                
                line = self.pitch_widget.scene.addLine(x1, y1, x2, y2, pen)
                line.setZValue(98)  # Above real ball trajectories
                self.pitch_widget.dynamic_items.append(line)
            
            # Final simulated ball position
            if ball_positions:
                final_x, final_y, final_frame = ball_positions[-1]
                
                if current_frame is None or current_frame < final_frame:
                    final_radius = CONFIG.BALL_RADIUS * 1.3
                    pen_color = QColor(ball_color)
                    pen_color.setAlphaF(1.0)
                    
                    # Destination ring
                    final_ball = self.pitch_widget.scene.addEllipse(
                        final_x - final_radius, final_y - final_radius,
                        final_radius * 2, final_radius * 2,
                        QPen(pen_color, 0.6, Qt.PenStyle.SolidLine),
                        QBrush(Qt.BrushStyle.NoBrush)
                    )
                    final_ball.setZValue(99)
                    self.pitch_widget.dynamic_items.append(final_ball)
