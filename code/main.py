# main.py
"""
Application entry point and main window.

`MainWindow` orchestrates data, rendering (pitch/overlays), timeline controls,
annotations, tactical simulation, camera controls, and theme/settings.
"""
import os
import sys
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSlider, QPushButton,
    QLabel, QComboBox, QCheckBox, QColorDialog, QSpinBox, QButtonGroup,
    QRadioButton, QGroupBox, QDoubleSpinBox, QToolButton, QMenu, QSizePolicy
)
from PyQt6.QtCore import QTimer, QEvent, QDir, QSize, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QFont, QAction

# Local imports
from pitch import PitchWidget
from annotation.annotation import ArrowAnnotationManager, RectangleZoneManager, EllipseZoneManager, ConeZoneManager
from annotation.arrow.arrow_properties import ArrowProperties
from annotation.zone_properties import ZoneProperties, ConeZoneProperties
from data_processing import load_data, extract_match_actions_from_events, format_match_time, compute_pressure
from trajectory import TrajectoryManager
from match_actions import ActionFilterBar, create_nav_button
from utils.frame_utils import FrameManager, PossessionTracker
from slider import TimelineWidget
from score_manager import ScoreManager
from tactical_simulation import TacticalSimulationManager
from theme_manager import ThemeManager, majority_light
from camera.camera_manager import CameraManager  
from camera.camera_controls import CameraControlWidget
from settings import SettingsManager, SettingsDialog
from config import *

import qt_material


# ===== Centralized data loading =====
data = load_data(
    DATA_PATH,
    FILE_NAME_POS,
    FILE_NAME_INFOS,
    FILE_NAME_EVENTS,
)

xy_objects         = data['xy_objects']
possession         = data['possession']
ballstatus         = data['ballstatus']
events             = data['events']
pitch_info         = data['pitch_info']
teams_df           = data['teams_df']
home_team_name     = data['home_name']
away_team_name     = data['away_name']
home_ids           = data['home_ids']
away_ids           = data['away_ids']
player_ids         = data['player_ids']
player_orientations= data['orientations']
dsam               = data['dsam']
ball_carrier_array = data['ball_carrier_array']
home_colors        = data['home_colors']
away_colors        = data['away_colors']
id2num             = data['id2num']
n_frames_firstHalf = data['n1']
n_frames_secondHalf= data['n2']
n_frames           = data['ntot']
last_positions     = {'Home': {pid: (np.nan, np.nan) for pid in home_ids}, 'Away': {pid: (np.nan, np.nan) for pid in away_ids}, 'Ball': (np.nan, np.nan)}

X_MIN, X_MAX = pitch_info.xlim
Y_MIN, Y_MAX = pitch_info.ylim


def get_frame_data(frame_number):
    """Map a global frame index to half-relative info.

    Parameters
    ----------
    frame_number : int
        Global frame index in [0, n_frames).

    Returns
    -------
    tuple[str, int, str]
        (half_key, half_relative_index, half_label)
        where half_key ∈ {"firstHalf","secondHalf"} and half_label ∈ {"1st Half","2nd Half"}.
    """
    if frame_number < n_frames_firstHalf:
        return "firstHalf", frame_number, "1st Half"
    else:
        return "secondHalf", frame_number - n_frames_firstHalf, "2nd Half"

def get_possession_for_frame(possession, half, frame_idx):
    """Return possession team for a half-relative frame.

    Parameters
    ----------
    possession : dict
        Floodlight-like structure with `.code` arrays per half (0 none, 1 Home, 2 Away).
    half : str
        "firstHalf" or "secondHalf".
    frame_idx : int
        Index within the half.

    Returns
    -------
    str | None
        "Home", "Away" or None if no possession.
    """
    poss_val = possession[half].code[frame_idx]
    if poss_val == 1:
        return "Home"
    elif poss_val == 2:
        return "Away"
    else:
        return None
    
def _detect_home_side_first_half(xy_objects, home_ids, away_ids):
    """Detect whether the Home team defends left or right in the first half.

    Strategy
    --------
    - Use the first N frames of the first half
    - Compute the per-frame median X of Home and Away (robust to outliers/NaNs)
    - Average medians across frames
    - If Home median < Away median ⇒ Home is on the left; else right

    Parameters
    ----------
    xy_objects : dict
        Positions per half and side.
    home_ids, away_ids : list[str]
        Player IDs.

    Returns
    -------
    {'left','right'}
        Side defended by the Home team in the first half.
    """
    try:
        xy_home = xy_objects['firstHalf']['Home'].xy
        xy_away = xy_objects['firstHalf']['Away'].xy
    except Exception:
        # Fallback assumption
        return 'left'
    n_frames = min(len(xy_home), len(xy_away))
    if n_frames <= 0:
        return 'left'
    n_use = 50
    home_meds = []
    away_meds = []
    for f in range(n_use):
        xs_home = []
        xs_away = []
        xh = xy_home[f]; xa = xy_away[f]
        for i, _pid in enumerate(home_ids):
            x = xh[2*i]
            if not np.isnan(x):
                xs_home.append(x)
        for i, _pid in enumerate(away_ids):
            x = xa[2*i]
            if not np.isnan(x):
                xs_away.append(x)
        if xs_home:
            home_meds.append(float(np.median(xs_home)))
        if xs_away:
            away_meds.append(float(np.median(xs_away)))
    if not home_meds or not away_meds:
        # Fallback to center split if something went wrong
        center_x = (X_MIN + X_MAX) / 2.0
        mean_home = np.nanmean([xy_home[0][2*i] for i, _ in enumerate(home_ids)])
        return 'left' if mean_home < center_x else 'right'
    home_avg = float(np.mean(home_meds))
    away_avg = float(np.mean(away_meds))
    return 'left' if home_avg < away_avg else 'right'

# Precompute team sides per half
_HOME_SIDE_FIRST = _detect_home_side_first_half(xy_objects, home_ids, away_ids)
_HOME_SIDE_SECOND = 'right' if _HOME_SIDE_FIRST == 'left' else 'left'
_SIDES_BY_HALF = {
    'firstHalf': {'Home': _HOME_SIDE_FIRST, 'Away': ('right' if _HOME_SIDE_FIRST == 'left' else 'left')},
    'secondHalf': {'Home': _HOME_SIDE_SECOND, 'Away': ('right' if _HOME_SIDE_SECOND == 'left' else 'left')},
}

def get_offside_line_x(xy_objects, half, frame_idx, possession_team, home_ids, away_ids, teams_df, last_positions):
    """Compute offside line X based on second-last defender toward own goal.

    Parameters
    ----------
    xy_objects : dict
        Positions per half and side.
    half : {'firstHalf','secondHalf'}
    frame_idx : int
        Index within the half.
    possession_team : str | None
        Team in possession ("Home"/"Away"). Determines defending side.
    home_ids, away_ids : list[str]
    teams_df : pandas.DataFrame
        Unused here (kept for compatibility).
    last_positions : dict
        Fallback last-known X per player if current X is NaN.

    Returns
    -------
    float | None
        X coordinate for the offside line, or None if unavailable.
    """
    defending_team = "Home" if possession_team == "Away" else "Away"
    player_ids_team = home_ids if defending_team == "Home" else away_ids
    # Which side this defending team occupies in this half
    defending_side = _SIDES_BY_HALF.get(half, {}).get(defending_team, 'left')

    # Get X for all 11 defending players (including GK)
    xy = xy_objects[half][defending_team].xy[frame_idx]
    x_coords = []
    for i, pid in enumerate(player_ids_team):
        x = xy[2*i]
        if np.isnan(x):
            x = last_positions[defending_team].get(pid, (np.nan, np.nan))[0]
        if not np.isnan(x):
            x_coords.append(x)

    if not x_coords:
        return None
    # Sort positions and choose second defender toward own goal line
    xs_sorted = sorted(x_coords)
    if defending_side == 'left':
        # Own goal on the left → smaller X are nearer own goal → take 2nd smallest
        chosen = xs_sorted[1] if len(xs_sorted) >= 2 else xs_sorted[0]
    else:
        # Own goal on the right → larger X are nearer own goal → take 2nd largest
        chosen = xs_sorted[-2] if len(xs_sorted) >= 2 else xs_sorted[-1]
    return chosen

class MainWindow(QWidget):
    """Main application window for Tactikz with timeline and tools panels."""
    def __init__(self):
        """Construct the main window and initialize UI/managers/state.

        Notes
        -----
        - Builds the left panel (score, theme switcher, pitch, timeline) and the
          right tools panel (camera controls, simulation, annotations).
        - Loads actions from events, precomputes and caches color themes, then
          applies the current theme.
        - Instantiates managers: frames, trajectories, annotations, tactical
          simulation, score, camera, and settings, and wires their signals.
        - Sets the initial camera view to "full" after the first render.
        """
        super().__init__()
        self.setWindowTitle("Tactikz")
        self.resize(1700, 1000)

        # Managers
        self.frame_manager = FrameManager(n_frames_firstHalf, n_frames_secondHalf, n_frames)
        self.trajectory_manager = None  # Initialized after pitch_widget
        self.annotation_manager = None
        self.tactical_manager = None  # Tactical simulation manager
        self.theme_mgr = ThemeManager(
            de_min=20.0,
        )
        self.score_manager = ScoreManager(events, home_team_name, away_team_name, n_frames_firstHalf, FPS)
        self.camera_manager = None  # Initialized after pitch_widget
        self.settings_manager = SettingsManager()
        self.settings_dialog = None
        self._settings_signal_connection = None

        # Context menu for arrows
        self.arrow_context_menu = None
        
        # State
        self.simulation_mode = False
        self.is_playing = False
        self.frame_step = 1
        self.current_tool = "select"
        self.simulation_start_frame = 0
        self.simulation_end_frame = 0
        self.simulation_loop_active = False

        # Actions
        self.actions_data = extract_match_actions_from_events(events, FPS, n_frames_firstHalf)
        
        self._setup_ui()
        self._setup_managers()
        self._connect_signals()
        # Precompute and cache themes at startup to remove latency when switching
        for _mode in ("CLASSIC", "BLACK & WHITE"):
            # Use current teams; cache key includes teams so it will be reused
            home_main = home_colors[home_ids[0]][0] if home_ids and home_ids[0] in home_colors else "#FFFFFF"
            home_sec  = home_colors[home_ids[0]][1] if home_ids and home_ids[0] in home_colors and len(home_colors[home_ids[0]]) > 1 else "#CCCCCC"
            away_main = away_colors[away_ids[0]][0] if away_ids and away_ids[0] in away_colors else "#000000"
            away_sec  = away_colors[away_ids[0]][1] if away_ids and away_ids[0] in away_colors and len(away_colors[away_ids[0]]) > 1 else "#444444"
            _ = self.theme_mgr.generate(_mode, home_main, away_main, home_sec, away_sec)
        # Apply current selection (now a cache hit)
        self.on_theme_mode_changed(self.theme_combo.currentText())


        self.update_scene(0)
        QTimer.singleShot(1, lambda: self.camera_manager.set_camera_mode("full", animate=False))



    def _setup_ui(self):
        """Build the main layout: score/theme row, pitch, filters, and timeline."""
        main_layout = QHBoxLayout(self)
        
        # Left panel
        left_panel = QVBoxLayout()
        # === NEW: Container for left side with fixed size ===
        left_container = QWidget()
        left_container.setFixedWidth(LEFT_PANEL_SIZE)  # ← FIXED SIZE (adjust as needed)
        left_container.setLayout(left_panel)

        score_layout = QHBoxLayout()
        score_layout.setSpacing(16)  # wider spacing for readability

        # SCORE on the left
        self.score_label = QLabel()
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._update_score_display(0)
        self.score_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        score_layout.addWidget(self.score_label)  # priority + large

        # Flexible spacer (takes all remaining space)
        score_layout.addStretch(1)

        # "Theme" (center/right, but before settings)
        theme_label = QLabel("Theme:")
        score_layout.addWidget(theme_label, 0)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["CLASSIC", "BLACK & WHITE"])
        self.theme_combo.setCurrentText("CLASSIC")
        self.theme_combo.setFixedWidth(160)
        self.theme_combo.currentTextChanged.connect(self.on_theme_mode_changed)
        score_layout.addWidget(self.theme_combo, 0)

        # Another small spacer for breathing room
        score_layout.addSpacing(8)

        # "Visual Settings" button ALL THE WAY TO THE RIGHT
        self.settings_button = QPushButton("Visual Settings")
        self.settings_button.setToolTip("Visual Settings")
        self.settings_button.clicked.connect(self._show_settings)
        self.settings_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        score_layout.addWidget(self.settings_button, 0)

        
        left_panel.addLayout(score_layout)
        
        # Pitch
        self.pitch_widget = PitchWidget(X_MIN, X_MAX, Y_MIN, Y_MAX)
        left_panel.addWidget(self.pitch_widget)
        
        # Action filtering bar
        self.action_filter = ActionFilterBar(self.actions_data, self._on_filter_update)
        left_panel.addLayout(self.action_filter.layout)
        
        # Timeline and controls
        self._create_timeline_controls(left_panel)
        
        # Right panel (tools) - SIMPLIFIED
        tools_panel = self._create_tools_panel()

        
        main_layout.addWidget(left_container)
        main_layout.addLayout(tools_panel)
    
    def _update_score_display(self, frame):
        """Update the score label with team colors and current score at frame."""
        home_score, away_score = self.score_manager.get_score_at_frame(frame)
        home_main_color = home_colors[home_ids[0]][0]
        away_main_color = away_colors[away_ids[0]][0]
        home_sec_color = home_colors[home_ids[0]][1]
        away_sec_color = away_colors[away_ids[0]][1]
        all_colors = [home_main_color, away_main_color, home_sec_color, away_sec_color]
        if majority_light(all_colors):
            background_color = "#000000"
            score_color = "#ffffff"
        else:
            background_color = "#ffffff"
            score_color = "#000000"
        
        score_html = f"""
        <span style="color: {home_main_color}; font-weight: bold;">{home_team_name}</span>
        <span style="color: {score_color}; font-weight: bold;"> {home_score} - {away_score} </span>
        <span style="color: {away_main_color}; font-weight: bold;">{away_team_name}</span>
        """
        
        self.score_label.setStyleSheet(f"""
            QLabel {{
                font-size: 20px;
                font-family: Arial;
                font-weight: bold;
                background: {background_color};
                padding: 6px 6px;
                border-radius: 6px;
            }}
        """)
        
        self.score_label.setText(score_html)
        self.score_label.adjustSize()

    
    def _create_timeline_controls(self, parent_layout):
        """Create timeline slider, nav buttons, speed, play/pause, and overlays.

        Parameters
        ----------
        parent_layout : QBoxLayout
            Layout to which the timeline controls will be added.
        """
        control_layout = QHBoxLayout()
        nav_layout = QHBoxLayout()
        nav_layout.addWidget(create_nav_button("< 1m", NAV_BUTTON_WIDTH, NAV_BUTTON_HEIGHT, -60 * FPS, "Back 1 minute", self.jump_frames))
        nav_layout.addWidget(create_nav_button("< 5s", NAV_BUTTON_WIDTH, NAV_BUTTON_HEIGHT, -5 * FPS, "Back 5 seconds", self.jump_frames))
        
        self.timeline_widget = TimelineWidget(n_frames, n_frames_firstHalf, n_frames_secondHalf)
        self.timeline_widget.frameChanged.connect(self.update_scene)
        self.timeline_widget.set_actions(self.actions_data)
        nav_layout.addWidget(self.timeline_widget)
        nav_layout.addWidget(create_nav_button("5s >", NAV_BUTTON_WIDTH, NAV_BUTTON_HEIGHT, 5 * FPS, "Forward 5 seconds", self.jump_frames))
        nav_layout.addWidget(create_nav_button("1m >", NAV_BUTTON_WIDTH, NAV_BUTTON_HEIGHT, 60 * FPS, "Forward 1 minute", self.jump_frames))

        control_layout.addLayout(nav_layout)


        # Speed control
        self.speed_box = QComboBox()
        self.speed_box.setMinimumWidth(80)
        self.speed_box.setMaximumWidth(80)
        for label, _ in [("x0.25", 160), ("x0.5", 80), ("x1", 40), ("x2", 20), ("x4", 10), ("x16", 5)]:
            self.speed_box.addItem(label)
        self.speed_box.setCurrentIndex(2)

        speed_widget = QWidget()
        speed_layout = QHBoxLayout(speed_widget)

        label_speed = QLabel("Speed")
        label_speed.setFixedWidth(label_speed.sizeHint().width())

        speed_layout.addWidget(label_speed)
        speed_layout.addWidget(self.speed_box)
        control_layout.addWidget(speed_widget)



        
        # Play/pause button
        self.play_icon = QIcon(os.path.join(SVG_DIR, "play.svg"))
        self.pause_icon = QIcon(os.path.join(SVG_DIR, "pause.svg"))

        self.play_button = QToolButton()
        self.play_button.setFixedWidth(60)
        self.play_button.setFixedHeight(60)
        self.play_button.setIcon(self.play_icon)
        self.play_button.setIconSize(QSize(24, 24))
        self.play_button.setText("")
        self.play_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        
        self.play_button.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                border: none;
                font-size: 9px;
                font-weight: bold;
                color: #888;
                padding-top: 10px;
                padding-bottom: 2px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
            QToolButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        control_layout.addWidget(self.play_button)

        # Checkboxes
        # === Visual overlays button with menu ===
        self.visual_overlays_button = QToolButton()
        self.visual_overlays_button.setText("Visual overlays")
        self.visual_overlays_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.visual_overlays_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.visual_overlays_button.setStyleSheet("""
        QToolButton {
            font-size: 12px;
            padding: 3px 6px;
            border: 1px solid #888;
            border-radius: 4px;
        }
        """)

        # Menu with checkable actions
        overlays_menu = QMenu(self.visual_overlays_button)

        # Orientation
        self.orientation_action = QAction("Orientation", self, checkable=True)
        self.orientation_action.setChecked(True)
        overlays_menu.addAction(self.orientation_action)

        # Offside
        self.offside_action = QAction("Offside", self, checkable=True)
        self.offside_action.setChecked(True)
        overlays_menu.addAction(self.offside_action)

        # Pressure
        self.pressure_action = QAction("Pressure (Ball Carrier)", self, checkable=True)
        self.pressure_action.setChecked(True)
        overlays_menu.addAction(self.pressure_action)

        self.visual_overlays_button.setMenu(overlays_menu)
        control_layout.addWidget(self.visual_overlays_button)
        
        self.orientation_action.toggled.connect(lambda _: self.update_scene(self.timeline_widget.value()))
        self.offside_action.toggled.connect(lambda _: self.update_scene(self.timeline_widget.value()))
        self.pressure_action.toggled.connect(lambda _: self.update_scene(self.timeline_widget.value()))

        # Info label
        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setFixedWidth(100)
        control_layout.addWidget(self.info_label)
        
        parent_layout.addLayout(control_layout)
        
        # Timer
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.next_frame)
    
    def _create_tools_panel(self):
        """Build the right tools panel (simulation, trajectories, annotation)."""
        tools_panel = QVBoxLayout()
        
        # Simulation mode
        tools_panel.addWidget(QLabel("Simulation"))
        self.simulation_button = QPushButton("Simulation Mode")
        self.simulation_button.setCheckable(True)
        self.simulation_button.clicked.connect(self.toggle_simulation_mode)
        tools_panel.addWidget(self.simulation_button)
        
        self.sim_interval_spin = QDoubleSpinBox()
        self.sim_interval_spin.setRange(1.0, 60.0)
        self.sim_interval_spin.setValue(10.0)
        self.sim_interval_spin.setSuffix(" sec")
        self.sim_interval_spin.setSingleStep(0.5)
        self.sim_interval_spin.valueChanged.connect(self.update_simulation_interval)
        tools_panel.addWidget(QLabel("Future interval:"))
        tools_panel.addWidget(self.sim_interval_spin)
        
        # Display loop times
        self.loop_times_label = QLabel("")
        self.loop_times_label.setWordWrap(True)
        self.loop_times_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
        tools_panel.addWidget(self.loop_times_label)
        
        self.show_trajectories_checkbox = QCheckBox("Show trajectories")
        self.show_trajectories_checkbox.setChecked(True)
        self.show_trajectories_checkbox.stateChanged.connect(lambda: self.update_scene(self.timeline_widget.value()))
        tools_panel.addWidget(self.show_trajectories_checkbox)

        self.simulation_info = QLabel("Click Play to loop the selected interval")
        self.simulation_info.setWordWrap(True)
        self.simulation_info.setStyleSheet("color: #888; font-size: 10px;")
        tools_panel.addWidget(self.simulation_info)
        
        # Annotation tools - SIMPLIFIED
        tools_panel.addWidget(QLabel("────────────────"))
        tools_panel.addWidget(QLabel("Annotation"))
        
        self.select_button = QPushButton("Selection")
        self.select_button.setCheckable(True)
        self.select_button.setChecked(True)
        self.select_button.clicked.connect(lambda: self.set_tool_mode("select"))
        tools_panel.addWidget(self.select_button)
        
        self.arrow_button = QPushButton("Arrow")
        self.arrow_button.setCheckable(True)
        self.arrow_button.clicked.connect(lambda: self.set_tool_mode("arrow"))
        tools_panel.addWidget(self.arrow_button)
        
        self.curve_button = QPushButton("Curved Arrow")
        self.curve_button.setCheckable(True)
        self.curve_button.clicked.connect(lambda: self.set_tool_mode("curve"))
        tools_panel.addWidget(self.curve_button)
        
        self.rectangle_zone_button = QPushButton("Rectangle Zone")
        self.rectangle_zone_button.setCheckable(True)
        self.rectangle_zone_button.clicked.connect(lambda: self.set_tool_mode("rectangle_zone"))
        tools_panel.addWidget(self.rectangle_zone_button)
        
        self.ellipse_zone_button = QPushButton("Ellipse Zone")
        self.ellipse_zone_button.setCheckable(True)
        self.ellipse_zone_button.clicked.connect(lambda: self.set_tool_mode("ellipse_zone"))
        tools_panel.addWidget(self.ellipse_zone_button)
        
        self.cone_zone_button = QPushButton("Cone Zone")
        self.cone_zone_button.setCheckable(True)
        self.cone_zone_button.clicked.connect(lambda: self.set_tool_mode("cone_zone"))
        tools_panel.addWidget(self.cone_zone_button)
        
        tools_panel.addStretch(1)
        
        return tools_panel
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Nothing custom yet; placeholder in case we need responsive tweaks





    def _setup_managers(self):
        """Create managers (trajectory, annotation, tactical, camera) and UI hooks."""
        self.trajectory_manager = TrajectoryManager(self.pitch_widget, home_colors, away_colors)
        self.annotation_manager = ArrowAnnotationManager(self.pitch_widget.scene)
        self.rectangle_zone_manager = RectangleZoneManager(self.pitch_widget.scene)
        self.ellipse_zone_manager = EllipseZoneManager(self.pitch_widget.scene)
        self.cone_zone_manager = ConeZoneManager(self.pitch_widget.scene)
        self.tactical_manager = TacticalSimulationManager(
            self.annotation_manager, self.pitch_widget, 
            home_ids, away_ids, home_colors, away_colors
        )
        self.camera_manager = CameraManager(self.pitch_widget)
        self.camera_control_widget = CameraControlWidget(self.camera_manager, self)
        # Integrate camera widget into the tools panel
        tools_layout = self.layout().itemAt(1).layout()  # Panel droit
        tools_layout.insertWidget(0, self.camera_control_widget)
        tools_layout.insertWidget(1, QLabel("────────────────"))
        
        # Removed sequencer controls per user request


        # Context menu for arrows
        self.arrow_context_menu = ArrowProperties(self)
        
        # Context menu for zones
        self.zone_context_menu = ZoneProperties(self)
        self.cone_zone_context_menu = ConeZoneProperties(self) 
        
        self._setup_arrow_context_menu()
        self._setup_zone_context_menu()
        
        self.set_tool_mode("select")
    
    def _setup_arrow_context_menu(self):
        """Prepare the arrow properties popup and wire its signals."""
        # Prepare player data with ALL colors
        home_players = {}
        away_players = {}
        
        for player_id in home_ids:
            number = id2num.get(player_id, "?")
            colors = home_colors.get(player_id, ["#FF0000", "#FFFFFF", "#000000"])
            main_color = colors[0]
            sec_color = colors[1] if len(colors) > 1 else colors[0]
            num_color = colors[2] if len(colors) > 2 else "#000000"
            home_players[player_id] = (number, main_color, sec_color, num_color)
        
        for player_id in away_ids:
            number = id2num.get(player_id, "?")
            colors = away_colors.get(player_id, ["#0000FF", "#FFFFFF", "#000000"])
            main_color = colors[0]
            sec_color = colors[1] if len(colors) > 1 else colors[0]
            num_color = colors[2] if len(colors) > 2 else "#000000"
            away_players[player_id] = (number, main_color, sec_color, num_color)
        
        self.arrow_context_menu.set_players_data(home_players, away_players)
        
        # Connect signals
        self.arrow_context_menu.fromPlayerSelected.connect(self._on_from_player_selected)
        self.arrow_context_menu.toPlayerSelected.connect(self._on_to_player_selected)
        self.arrow_context_menu.deleteRequested.connect(self._on_arrow_delete_requested)
        self.arrow_context_menu.propertiesConfirmed.connect(self._on_arrow_properties_confirmed)
        
    # Removed sequencer handler per user request
    
    def _connect_signals(self):
        """Connect UI controls, timer, and camera widget signals."""
        self.play_button.clicked.connect(self.toggle_play_pause)
        self.speed_box.currentIndexChanged.connect(self.update_speed)
        # === NEW: Camera signals ===
        self.camera_control_widget.modeChanged.connect(self._on_camera_mode_changed)
        self.camera_control_widget.zoomInRequested.connect(self._on_zoom_in)
        self.camera_control_widget.zoomOutRequested.connect(self._on_zoom_out)
        self.camera_control_widget.resetZoomRequested.connect(self._on_reset_zoom)

        
        # Event filters
        self.installEventFilter(self)
        self.pitch_widget.view.viewport().installEventFilter(self)
        self.pitch_widget.view.viewport().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.pitch_widget.view.viewport().setFocus()
    




    def _on_filter_update(self):
        """Refresh timeline markers when action type filters change."""
        active_actions = self.action_filter.get_filtered_actions()
        active_types = self.action_filter.get_active_types()
        self.timeline_widget.set_filtered_types(active_types)

    def toggle_simulation_mode(self):
        """Turn tactical simulation mode on/off and (re)configure the loop."""
        self.simulation_mode = self.simulation_button.isChecked()
        if self.simulation_mode:
            self._pause_match()
            current_frame = self.timeline_widget.value()
            interval_frames = int(self.sim_interval_spin.value() * FPS)
            
            self.simulation_start_frame = current_frame
            self.simulation_end_frame = min(current_frame + interval_frames, n_frames - 1)
            self.simulation_loop_active = False
            
            self.annotation_manager.set_tactical_mode(True)
            self._update_loop_times_display()
            self.play_button.setText("▶ Loop")
        else:
            self.trajectory_manager.clear_trails()
            self.simulation_loop_active = False
            self.play_button.setText("")
            self.loop_times_label.setText("")
            
            self.annotation_manager.set_tactical_mode(False)
            self.tactical_manager.clear_tactical_data()
            
        self.update_scene(self.timeline_widget.value())

    def _update_loop_times_display(self):
        """Update the small label that shows the loop start and end times."""
        start_time = format_match_time(self.simulation_start_frame, n_frames_firstHalf, n_frames_secondHalf, 0, 0, fps=FPS)
        end_time = format_match_time(self.simulation_end_frame, n_frames_firstHalf, n_frames_secondHalf, 0, 0, fps=FPS)
        self.loop_times_label.setText(f"Loop: {start_time} → {end_time}")

    def update_simulation_interval(self, value):
        """Change the future interval (in seconds) and recompute loop bounds.

        Parameters
        ----------
        value : float
            Interval in seconds to preview or simulate.
        """
        if self.simulation_mode:
            current_frame = self.simulation_start_frame
            interval_frames = int(value * FPS)
            self.simulation_end_frame = min(current_frame + interval_frames, n_frames - 1)
            
            self._update_loop_times_display()
            
            if not self.is_playing:
                self.update_scene(self.timeline_widget.value())

    def update_scene(self, frame_number):
        """Redraw everything for a global frame: pitch, players, ball, overlays.

        Parameters
        ----------
        frame_number : int
            Global frame index to render.
        """
        self._update_score_display(frame_number)
        
        if (self.simulation_mode and 
            not self.is_playing and 
            abs(frame_number - self.simulation_start_frame) > 5):
            
            interval_frames = int(self.sim_interval_spin.value() * FPS)
            self.simulation_start_frame = frame_number
            self.simulation_end_frame = min(frame_number + interval_frames, n_frames - 1)
            self.simulation_loop_active = False
            self._update_loop_times_display()
        
        self.pitch_widget.clear_dynamic()
        self.pitch_widget.draw_pitch()
        
        half, idx, halftime = self.frame_manager.get_frame_data(frame_number)
        
        # Simulation mode: trajectories rendering
        if self.simulation_mode and self.show_trajectories_checkbox.isChecked():
            if self.tactical_manager.tactical_arrows and not SIMULATION_ONLY_ARROWS:
                self.tactical_manager.calculate_simulated_trajectories(
                    self.sim_interval_spin.value(),
                    self.simulation_start_frame,
                    xy_objects,
                    n_frames,
                    self.frame_manager.get_frame_data
                )
                simulated_data = self.tactical_manager.get_simulated_trajectories()
                self.trajectory_manager.draw_simulated_trajectories(
                    simulated_data,
                    frame_number,
                    self.simulation_start_frame,
                    self.simulation_end_frame,
                    ball_color=self.settings_manager.ball_color
                )
            else:
                self.trajectory_manager.calculate_future_trajectories(
                    self.simulation_start_frame,
                    self.sim_interval_spin.value(),
                    xy_objects,
                    home_ids,
                    away_ids,
                    n_frames,
                    self.frame_manager.get_frame_data
                )
                self.trajectory_manager.draw_future_trajectories(
                    current_frame=frame_number,
                    loop_start=self.simulation_start_frame,
                    loop_end=self.simulation_end_frame,
                    ball_color=self.settings_manager.ball_color
                )
        
        # Draw players
        self._draw_players(half, idx)
        
        # Ball
        ball_xy = xy_objects[half]["Ball"].xy[idx]
        ball_x, ball_y = ball_xy[0], ball_xy[1]
        self.pitch_widget.draw_ball(ball_x, ball_y, color=self.settings_manager.ball_color)
        
        self.camera_manager.update_ball_position(ball_x, ball_y)
        
        # Offside
        possession_team = PossessionTracker.get_possession_for_frame(possession, half, idx)
        offside_x = get_offside_line_x(xy_objects, half, idx, possession_team, 
                                    home_ids, away_ids, teams_df, last_positions)
        self.pitch_widget.draw_offside_line(offside_x, visible=self.offside_action.isChecked(), color=self.settings_manager.offside_color)
        self.pitch_widget.draw_pressure_for_ball_carrier(xy_objects, home_ids,
                                                away_ids, dsam, player_orientations, half, idx, ball_xy,
                                                compute_pressure, ball_carrier_array, ballstatus=ballstatus, frame_number=frame_number,
                                                visible=self.pressure_action.isChecked(),
                )

    
        # Info
        match_time = format_match_time(frame_number, n_frames_firstHalf, 
                                    n_frames_secondHalf, 0, 0, fps=FPS)
        

        self.info_label.setText(f"{halftime} \n{match_time}  \nFrame {get_frame_data(frame_number)[1]}")

    def _draw_players(self, half, idx):
        """Draw all players for a half/index with colors, numbers, and orientation.

        Parameters
        ----------
        half : {'firstHalf','secondHalf'}
            Current half.
        idx : int
            Frame index within the half.
        """
        for side, ids, colors in [("Home", home_ids, home_colors), 
                                 ("Away", away_ids, away_colors)]:
            xy = xy_objects[half][side].xy[idx]
            for i, pid in enumerate(ids):
                try:
                    x, y = xy[2*i], xy[2*i+1]
                    if not np.isnan(x) and not np.isnan(y):
                        main, sec, numc = colors[pid]
                        num = id2num.get(pid, "")
                        self.pitch_widget.draw_player(
                            x=x, y=y, 
                            main_color=main, sec_color=sec, num_color=numc, 
                            number=num,
                            angle=player_orientations[pid][self.timeline_widget.value()],
                            velocity=dsam[side][pid][half]['S'][idx],
                            display_orientation=self.orientation_action.isChecked(),
                            z_offset=(10 if side == "Home" else 50) + i,
                            arrow_color=self.settings_manager.arrow_color
                        )
                except IndexError:
                    continue
    
    def jump_frames(self, n):
        """Jump forward/backward by N frames, respecting simulation loop rules.

        Parameters
        ----------
        n : int
            Number of frames to move (+ forward, − backward).
        """
        if self.simulation_mode and self.is_playing:
            return
            
        new_frame = np.clip(self.timeline_widget.value() + n, 0, n_frames-1)
        self.timeline_widget.setValue(new_frame)
        
        if self.simulation_mode:
            interval_frames = int(self.sim_interval_spin.value() * FPS)
            self.simulation_start_frame = new_frame
            self.simulation_end_frame = min(new_frame + interval_frames, n_frames - 1)
            self.simulation_loop_active = False
            self._update_loop_times_display()

    def toggle_play_pause(self):
        """Toggle playback. In simulation, toggles the loop state text as well."""
        if self.is_playing:
            self.play_button.setIcon(self.play_icon)
            if self.simulation_mode:
                self.play_button.setText("▶ Loop")
            else:
                self.play_button.setText("")
            self.timer.stop()
        else:
            self.play_button.setIcon(self.pause_icon)
            if self.simulation_mode:
                self.simulation_loop_active = True
                self.play_button.setText("⏸ Loop")
            else:
                self.play_button.setText("")
            self.timer.start()
        self.is_playing = not self.is_playing

    def update_speed(self, idx):
        """Set timer interval from speed combo (index → milliseconds).

        Parameters
        ----------
        idx : int
            Index into predefined timer intervals.
        """
        intervals = [160, 80, 40, 20, 10, 5]
        self.timer.setInterval(intervals[idx])

    def next_frame(self):
        """Advance playback by one step, looping if simulation loop is active."""
        current_frame = self.timeline_widget.value()
        
        if self.simulation_mode and self.simulation_loop_active:
            if current_frame >= self.simulation_end_frame:
                self.toggle_play_pause()
                next_frame = self.simulation_start_frame
            else:
                next_frame = min(current_frame + self.frame_step, self.simulation_end_frame)
        else:
            next_frame = min(current_frame + self.frame_step, n_frames - 1)
            
            if next_frame == n_frames - 1:
                self.toggle_play_pause()
        
        self.timeline_widget.setValue(next_frame)

    def _pause_match(self):
        """Pause playback if currently playing (helper used by tools)."""
        if self.is_playing:
            self.toggle_play_pause()

    # Annotation methods
    def set_tool_mode(self, mode):
        """Switch between select/arrow/curve tools and update cursor + state.

        Parameters
        ----------
        mode : {'select','arrow','curve','rectangle_zone','ellipse_zone'}
            Tool to activate.
        """
        self.current_tool = mode
        self.select_button.setChecked(mode == "select")
        self.arrow_button.setChecked(mode == "arrow")
        self.curve_button.setChecked(mode == "curve")
        self.rectangle_zone_button.setChecked(mode == "rectangle_zone")
        self.ellipse_zone_button.setChecked(mode == "ellipse_zone")
        self.cone_zone_button.setChecked(mode == "cone_zone")
        self.pitch_widget.view.setCursor(Qt.CursorShape.ArrowCursor if mode == "select" else Qt.CursorShape.CrossCursor)
        
        if mode == "select":
            self.annotation_manager.try_finish_arrow()
            self.rectangle_zone_manager.cancel_zone()
            self.ellipse_zone_manager.cancel_zone()
            self.cone_zone_manager.cancel_zone()
            # Disable mouse tracking in select to reduce event noise
            try:
                self.pitch_widget.view.setMouseTracking(False)
                self.pitch_widget.view.viewport().setMouseTracking(False)
            except Exception:
                pass
        if mode in ("arrow", "curve"):
            self._pause_match()
            self.rectangle_zone_manager.set_mode("select")
            self.ellipse_zone_manager.set_mode("select")
            self.cone_zone_manager.set_mode("select")
            # Ensure we receive move events without holding mouse button
            try:
                self.pitch_widget.view.setMouseTracking(True)
                self.pitch_widget.view.viewport().setMouseTracking(True)
            except Exception:
                pass
        if mode in ("rectangle_zone", "ellipse_zone", "cone_zone"):
            self._pause_match()
            if mode == "rectangle_zone":
                self.rectangle_zone_manager.set_mode("create")
            elif mode == "ellipse_zone":
                self.ellipse_zone_manager.set_mode("create")
            else:
                self.cone_zone_manager.set_mode("create")
            self.annotation_manager.set_mode("select")
            # Ensure we receive move events without holding mouse button
            try:
                self.pitch_widget.view.setMouseTracking(True)
                self.pitch_widget.view.viewport().setMouseTracking(True)
            except Exception:
                pass
        
        if mode not in ("rectangle_zone", "ellipse_zone"):
            self.annotation_manager.set_mode(mode)
        self.pitch_widget.view.viewport().setFocus()
    
    # Methods for arrow context menu
    def _on_from_player_selected(self, player_id):
        """Handle selection of the origin player for the current arrow."""
        if self.arrow_context_menu.current_arrow:
            current_frame = self.timeline_widget.value()
            result = self.tactical_manager.associate_arrow_with_player(
                self.arrow_context_menu.current_arrow, player_id, current_frame, xy_objects
            )
    
    def _on_to_player_selected(self, player_id):
        """Handle selection of the receiving player for a pass arrow."""
        success = self.tactical_manager.set_pass_receiver(player_id)

    
    def _on_arrow_color_changed(self, color):
        """Change color of the selected arrow from the properties popup."""
        if self.arrow_context_menu.current_arrow:
            self.annotation_manager.selected_arrow = self.arrow_context_menu.current_arrow
            self.annotation_manager.set_color(color)
    
    def _on_arrow_width_changed(self, width):
        """Change width of the selected arrow from the properties popup."""
        if self.arrow_context_menu.current_arrow:
            self.annotation_manager.selected_arrow = self.arrow_context_menu.current_arrow
            self.annotation_manager.set_width(width)
    
    def _on_arrow_style_changed(self, style):
        """Change style (solid/dotted/zigzag) of the selected arrow."""
        if self.arrow_context_menu.current_arrow:
            self.annotation_manager.selected_arrow = self.arrow_context_menu.current_arrow
            self.annotation_manager.set_style(style)
            # Update the style stored in the new arrow
            if self.annotation_manager.selected_arrow:
                self.annotation_manager.selected_arrow.arrow_style = style
                # Update the reference in the context menu
                self.arrow_context_menu.current_arrow = self.annotation_manager.selected_arrow
    
    def _on_arrow_delete_requested(self):
        """Delete the currently selected arrow and clean its tactical links."""
        if self.arrow_context_menu.current_arrow:
            arrow = self.arrow_context_menu.current_arrow
            # Clean up handles first
            arrow.cleanup_handles()
            # Remove from the arrows list
            if arrow in self.annotation_manager.arrows:
                self.annotation_manager.arrows.remove(arrow)
            # Remove from the scene
            try:
                self.pitch_widget.scene.removeItem(arrow)
            except RuntimeError:
                pass
            # Remove tactical association if it exists
            self.tactical_manager.remove_arrow_association(arrow)
            # Clear selection
            self.annotation_manager.clear_selection()
        self.arrow_context_menu.close()
    
    # === NEW: Camera event handlers ===
    def _on_camera_mode_changed(self, mode):
        """Update camera preset when a mode button is clicked.

        Parameters
        ----------
        mode : str
            Camera mode key.
        """
        success = self.camera_manager.set_camera_mode(mode, animate=True)
        if success:
            # Update ball tracking status
            is_following = (mode == "ball")
            self.camera_control_widget.update_ball_status(is_following)
    
    def _on_zoom_in(self):
        """Zoom in the pitch view slightly."""
        self.camera_manager.zoom_in(1.2)
    
    def _on_zoom_out(self):
        """Zoom out the pitch view slightly."""
        self.camera_manager.zoom_out(0.83)
    
    def _on_reset_zoom(self):
        """Reset camera to full pitch and sync the control widget state."""
        self.camera_manager.reset_zoom()
        self.camera_control_widget.set_mode("full")

    
    # Event handling
    def keyPressEvent(self, event):
        """If a drawing tool is active, finish/cancel and return to Select on keypress."""
        if self.current_tool != "select":
            self.annotation_manager.try_finish_arrow()
            self.set_tool_mode("select")
            return
        super().keyPressEvent(event)
    


    def eventFilter(self, obj, event):
        """Route mouse events to selection/creation logic depending on tool.

        Parameters
        ----------
        obj : QObject
            Watched object.
        event : QEvent
            Event received.

        Returns
        -------
        bool
            True if the event is fully handled here; otherwise False.
        """
        if obj != self.pitch_widget.view.viewport():
            return False
        
        if self.current_tool == "select":
            # In select mode: handle only initial clicks
            if event.type() == QEvent.Type.MouseButtonPress:
                scene_pos = self.pitch_widget.view.mapToScene(event.position().toPoint())
                clicked_arrow = self._find_arrow_at_position(scene_pos)
                clicked_zone = self._find_zone_at_position(scene_pos)
                

                                
                if event.button() == Qt.MouseButton.LeftButton:
                    if clicked_arrow:
                        # Simple left click: select only
                        self.annotation_manager.select_arrow(clicked_arrow)
                        self.rectangle_zone_manager.clear_selection()
                        self.ellipse_zone_manager.clear_selection()
                        self.cone_zone_manager.clear_selection()
                        # IMPORTANT: Don't return True here to allow dragging
                        return False  # Let Qt handle drag & drop
                    elif clicked_zone:
                        # Select zone
                        self.annotation_manager.clear_selection()
                        if clicked_zone in self.rectangle_zone_manager.zones:
                            self.rectangle_zone_manager.select_zone(clicked_zone)
                            self.ellipse_zone_manager.clear_selection()
                            self.cone_zone_manager.clear_selection()
                        elif clicked_zone in self.ellipse_zone_manager.zones:
                            self.ellipse_zone_manager.select_zone(clicked_zone)
                            self.rectangle_zone_manager.clear_selection()
                            self.cone_zone_manager.clear_selection()
                        else:
                            self.cone_zone_manager.select_zone(clicked_zone)
                            self.rectangle_zone_manager.clear_selection()
                            self.ellipse_zone_manager.clear_selection()
                        return False  # Let Qt handle drag & drop
                    else:
                        # Click on empty area: clear selection
                        self.annotation_manager.clear_selection()
                        self.rectangle_zone_manager.clear_selection()
                        self.ellipse_zone_manager.clear_selection()
                        self.cone_zone_manager.clear_selection()
                        return True  # We can intercept this
                        
                elif event.button() == Qt.MouseButton.RightButton:
                    if clicked_arrow:
                        # Right click: select AND open properties menu
                        self.annotation_manager.select_arrow(clicked_arrow)
                        self.rectangle_zone_manager.clear_selection()
                        self.ellipse_zone_manager.clear_selection()
                        self.cone_zone_manager.clear_selection()
                        
                        global_pos = self.pitch_widget.view.mapToGlobal(event.position().toPoint())
                        # Adjust position to keep menu within screen bounds
                        screen = QApplication.primaryScreen()
                        screen_geometry = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                        if global_pos.x() + 300 > screen_geometry.width():
                            global_pos.setX(global_pos.x() - 300)
                        if global_pos.y() + 500 > screen_geometry.height():
                            global_pos.setY(global_pos.y() - 500)
                        
                        self.arrow_context_menu.show_for_arrow(clicked_arrow, global_pos)
                        return True
                    elif clicked_zone:

                        # Right click: select AND open zone properties menu
                        self.annotation_manager.clear_selection()
                        if clicked_zone in self.rectangle_zone_manager.zones:
                            self.rectangle_zone_manager.select_zone(clicked_zone)
                            self.ellipse_zone_manager.clear_selection()
                            self.cone_zone_manager.clear_selection()
                            menu = self.zone_context_menu
                        elif clicked_zone in self.ellipse_zone_manager.zones:
                            self.ellipse_zone_manager.select_zone(clicked_zone)
                            self.rectangle_zone_manager.clear_selection()
                            self.cone_zone_manager.clear_selection()
                            menu = self.zone_context_menu
                        else:
                            self.cone_zone_manager.select_zone(clicked_zone)
                            self.rectangle_zone_manager.clear_selection()
                            self.ellipse_zone_manager.clear_selection()
                            menu = self.cone_zone_context_menu 
                        
                        global_pos = self.pitch_widget.view.mapToGlobal(event.position().toPoint())
                        # Adjust position to keep menu within screen bounds
                        screen = QApplication.primaryScreen()
                        screen_geometry = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                        if global_pos.x() + 300 > screen_geometry.width():
                            global_pos.setX(global_pos.x() - 300)
                        if global_pos.y() + 500 > screen_geometry.height():
                            global_pos.setY(global_pos.y() - 500)
                        

                        menu.show_for_zone(clicked_zone, global_pos)
                        return True
            # IMPORTANT: Do not intercept move events in select mode
            # to allow drag & drop of selected arrows
            return False
        
        # Arrow creation modes (arrow/curve) - existing logic
        if self.current_tool in ("arrow", "curve"):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    scene_pos = self.pitch_widget.view.mapToScene(event.position().toPoint())
                    self.annotation_manager.add_point(scene_pos)
                    
                    if not self.annotation_manager.arrow_curved and len(self.annotation_manager.arrow_points) == 2:
                        new_arrow = self.annotation_manager.finish_arrow()
                        # If in simulation mode, immediately prompt for associations
                        if new_arrow and self.simulation_mode:
                            # Determine action type based on style
                            action_type = self.tactical_manager.get_action_type(new_arrow)
                            # Prepare player datasets for selection
                            home_players = {}
                            away_players = {}
                            for player_id in home_ids:
                                number = id2num.get(player_id, "?")
                                main_color, sec_color, num_color = home_colors.get(player_id, ("#4CAF50", "#2E7D32", "#FFFFFF"))
                                home_players[player_id] = (number, main_color, sec_color, num_color)
                            for player_id in away_ids:
                                number = id2num.get(player_id, "?")
                                main_color, sec_color, num_color = away_colors.get(player_id, ("#F44336", "#B71C1C", "#FFFFFF"))
                                away_players[player_id] = (number, main_color, sec_color, num_color)

                            # Show selection dialog(s) according to action type
                            from annotation.arrow.arrow_player_selection import ArrowPlayerSelection
                            # Compute default candidates: nearest to start/end
                            start_pt = new_arrow.arrow_points[0]
                            end_pt = new_arrow.arrow_points[-1]
                            default_from = self.tactical_manager.find_player_at_position(start_pt, self.timeline_widget.value(), xy_objects, self.frame_manager.get_frame_data)
                            default_to = self.tactical_manager.find_player_at_position(end_pt, self.timeline_widget.value(), xy_objects, self.frame_manager.get_frame_data) if action_type == 'pass' else None

                            # From player (always)
                            dlg_from = ArrowPlayerSelection(home_players, away_players, title="Select From Player", parent=self, default_selected_id=default_from)
                            if dlg_from.exec() == dlg_from.DialogCode.Accepted:
                                from_id = dlg_from.selected_player_id
                                if from_id:
                                    current_frame = self.timeline_widget.value()
                                    self.tactical_manager.associate_arrow_with_player(new_arrow, from_id, current_frame, xy_objects)
                                    # Color the arrow with the team's main color
                                    if from_id in home_ids:
                                        team_color = home_colors.get(from_id, ["#4CAF50"])[0]
                                    else:
                                        team_color = away_colors.get(from_id, ["#F44336"])[0]
                                    new_arrow.set_color(team_color)
                                    if hasattr(new_arrow, 'refresh_visual'):
                                        new_arrow.refresh_visual()
                            # For pass: also select receiver
                            if action_type == 'pass':
                                dlg_to = ArrowPlayerSelection(home_players, away_players, title="Select To Player", parent=self, default_selected_id=default_to)
                                if dlg_to.exec() == dlg_to.DialogCode.Accepted:
                                    to_id = dlg_to.selected_player_id
                                    if to_id:
                                        self.tactical_manager.set_pass_receiver(to_id)

                            # Refresh simulated preview immediately
                            if self.show_trajectories_checkbox.isChecked():
                                self.update_scene(self.timeline_widget.value())
                        self.set_tool_mode("select")
                elif event.button() == Qt.MouseButton.RightButton:
                    if len(self.annotation_manager.arrow_points) < 2:
                        self.annotation_manager.cancel_arrow()
                        self.set_tool_mode("select")
                return True
            
            elif event.type() == QEvent.Type.MouseMove and self.annotation_manager.arrow_points:
                scene_pos = self.pitch_widget.view.mapToScene(event.position().toPoint())
                self.annotation_manager.update_preview(scene_pos)
                return True
        
        # Zone creation modes (rectangle/ellipse/cone)
        elif self.current_tool in ("rectangle_zone", "ellipse_zone", "cone_zone"):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    try:
                        self.pitch_widget.view.setMouseTracking(True)
                        self.pitch_widget.view.viewport().setMouseTracking(True)
                    except Exception:
                        pass
                    scene_pos = self.pitch_widget.view.mapToScene(event.position().toPoint())
                    if self.current_tool == "rectangle_zone":
                        self.rectangle_zone_manager.add_point(scene_pos)
                        self.rectangle_zone_manager.update_preview(scene_pos)
                    elif self.current_tool == "ellipse_zone":
                        self.ellipse_zone_manager.add_point(scene_pos)
                        self.ellipse_zone_manager.update_preview(scene_pos)
                    else:
                        self.cone_zone_manager.add_point(scene_pos)
                        self.cone_zone_manager.update_preview(scene_pos)
                elif event.button() == Qt.MouseButton.RightButton:
                    if self.current_tool == "rectangle_zone":
                        self.rectangle_zone_manager.cancel_zone()
                    elif self.current_tool == "ellipse_zone":
                        self.ellipse_zone_manager.cancel_zone()
                    else:
                        self.cone_zone_manager.cancel_zone()
                    self.set_tool_mode("select")
                return True
            
            elif event.type() == QEvent.Type.MouseMove:
                scene_pos = self.pitch_widget.view.mapToScene(event.position().toPoint())
                if self.current_tool == "rectangle_zone":
                    self.rectangle_zone_manager.update_preview(scene_pos)
                elif self.current_tool == "ellipse_zone":
                    self.ellipse_zone_manager.update_preview(scene_pos)
                else:
                    self.cone_zone_manager.update_preview(scene_pos)
                return True
            
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    if self.current_tool == "rectangle_zone":
                        if self.rectangle_zone_manager.finish_zone():
                            self.set_tool_mode("select")
                    elif self.current_tool == "ellipse_zone":
                        if self.ellipse_zone_manager.finish_zone():
                            self.set_tool_mode("select")
                    else:
                        if self.cone_zone_manager.finish_zone():
                            self.set_tool_mode("select")
                return True
        
        return False
    
    def _find_arrow_at_position(self, scene_pos):
        """Look for an arrow item under the pointer within a small tolerance box.

        Parameters
        ----------
        scene_pos : QPointF
            Position in scene coordinates.

        Returns
        -------
        QGraphicsItemGroup | None
            The arrow item if found; otherwise None.
        """
        # Search scene items within a tolerance zone
        tolerance = 5.0  # pixels tolerance
        search_rect = QRectF(scene_pos.x() - tolerance, scene_pos.y() - tolerance, 
                           tolerance * 2, tolerance * 2)
        items = self.pitch_widget.scene.items(search_rect)
        
        for item in items:
            # Check if the item is an arrow or part of an arrow
            parent = item
            while parent:
                if parent in self.annotation_manager.arrows:
                    return parent
                parent = parent.parentItem()
        
        return None

    def _find_zone_at_position(self, scene_pos):
        """Look for a zone item under the pointer within a small tolerance box.

        Parameters
        ----------
        scene_pos : QPointF
            Position in scene coordinates.

        Returns
        -------
        QGraphicsItemGroup | None
            The zone item if found; otherwise None.
        """
        # Search scene items within a tolerance zone
        tolerance = 5.0  # pixels tolerance (increased for easier detection)
        search_rect = QRectF(scene_pos.x() - tolerance, scene_pos.y() - tolerance, 
                           tolerance * 2, tolerance * 2)
        items = self.pitch_widget.scene.items(search_rect)
        

        
        for item in items:
            # Check if the item is a zone or part of a zone
            parent = item
            while parent:
                if (parent in self.rectangle_zone_manager.zones or
                    parent in self.ellipse_zone_manager.zones or
                    parent in self.cone_zone_manager.zones):
                    return parent
                parent = parent.parentItem()
        

        return None


    def _on_arrow_properties_confirmed(self):
            """Called when the properties popup is confirmed (no extra action needed)."""
            # The menu will close automatically
            pass

    def _on_zone_delete_requested(self):
        """Handle zone deletion request."""
        if self.rectangle_zone_manager.selected_zone:
            self.rectangle_zone_manager.delete_selected_zone()
        elif self.ellipse_zone_manager.selected_zone:
            self.ellipse_zone_manager.delete_selected_zone()
        elif self.cone_zone_manager.selected_zone:  # +++
            self.cone_zone_manager.delete_selected_zone()
        self.zone_context_menu.hide()
        self.cone_zone_context_menu.hide()

    def _on_zone_properties_confirmed(self):
        """Called when the zone properties popup is confirmed."""

        self.zone_context_menu.hide()

    def _setup_zone_context_menu(self):
        """Setup the zone context menu signals."""
        # Connect zone signals
        self.zone_context_menu.deleteRequested.connect(self._on_zone_delete_requested)
        self.zone_context_menu.propertiesConfirmed.connect(self._on_zone_properties_confirmed)
        # cone menu
        self.cone_zone_context_menu.deleteRequested.connect(self._on_zone_delete_requested)
        self.cone_zone_context_menu.propertiesConfirmed.connect(self._on_zone_properties_confirmed)
    
    def on_theme_mode_changed(self, new_mode: str):
        """Regenerate theme given team colors and refresh the scene and settings UI."""
        # Get primary and secondary colors
        home_main = home_colors[home_ids[0]][0] if home_ids and home_ids[0] in home_colors else "#FFFFFF"
        home_sec  = home_colors[home_ids[0]][1] if home_ids and home_ids[0] in home_colors and len(home_colors[home_ids[0]]) > 1 else "#CCCCCC"
        away_main = away_colors[away_ids[0]][0] if away_ids and away_ids[0] in away_colors else "#000000"
        away_sec  = away_colors[away_ids[0]][1] if away_ids and away_ids[0] in away_colors and len(away_colors[away_ids[0]]) > 1 else "#444444"
        self.current_theme = self.theme_mgr.generate(new_mode, home_main, away_main, home_sec, away_sec)
        self.pitch_widget.theme = self.current_theme
        self.settings_manager.reset_theme_colors(self.current_theme)
        current = self.timeline_widget.value()
        self.update_scene(current)
        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.settings_dialog._load_current_settings()


    def _show_settings(self):
        """Show (or focus) the non-modal Visual Settings dialog."""
        # If the dialog already exists and is visible, just raise it
        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return

        # Otherwise create a new dialog
        self.settings_dialog = SettingsDialog(self.settings_manager, self)
        # Connect the signal and keep a reference to later disconnect
        if self._settings_signal_connection is not None:
            try:
                self.settings_manager.settingsChanged.disconnect(self._settings_signal_connection)
            except Exception:
                pass
        self._settings_signal_connection = lambda: self.update_scene(self.timeline_widget.value())
        self.settings_manager.settingsChanged.connect(self._settings_signal_connection)
        self.settings_dialog.destroyed.connect(self._on_settings_dialog_destroyed)
        self.settings_dialog.show()

    def _on_settings_dialog_destroyed(self):
        """Disconnect temporary signals when the settings dialog is closed/destroyed."""
        # Disconnect the slot
        if self._settings_signal_connection is not None:
            try:
                self.settings_manager.settingsChanged.disconnect(self._settings_signal_connection)
            except Exception:
                pass
            self._settings_signal_connection = None
        self.settings_dialog = None



if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Ensure import order: PyQt first, then qt_material
    qt_material.apply_stylesheet(app, theme='dark_blue.xml', invert_secondary=False)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())