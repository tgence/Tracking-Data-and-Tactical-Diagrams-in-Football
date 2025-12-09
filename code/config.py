# config.py
"""
Global configuration and constants for the application.

This module defines:
- Project paths (code, project root, SVG, data)
- File names for Floodlight XML inputs (positions, match info, events)
- Visual and pitch geometry constants
- A dynamic configuration singleton (`CONFIG`) that scales UI-dependent sizes
- Time and UI constants (FPS, timeline sizes)

Only metadata and constants are defined here; no runtime logic.
"""

from PyQt6.QtCore import Qt
import os

# Paths / Loading
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CODE_DIR)
SVG_DIR = os.path.join(PROJECT_ROOT, "svgs/")
DATA_PATH = os.path.join(PROJECT_ROOT, "data/")

MATCH_ID = "J03WN1"
FILE_NAME_POS = f"DFL_04_03_positions_raw_observed_DFL-COM-000001_DFL-MAT-{MATCH_ID}.xml"
FILE_NAME_INFOS = f"DFL_02_01_matchinformation_DFL-COM-000001_DFL-MAT-{MATCH_ID}.xml"
FILE_NAME_EVENTS = f"DFL_03_02_events_raw_DFL-COM-000001_DFL-MAT-{MATCH_ID}.xml"

# Panel size
LEFT_PANEL_SIZE = 1200  


# Display
SCENE_EXTRA_GRASS = 48
LINE_WIDTH = 0.25

# Zones
GOAL_DEPTH = 2.44
GOAL_WIDTH = 7.32
PENALTY_AREA_LENGTH = 16.5
PENALTY_AREA_WIDTH = 40.3
GOAL_AREA_LENGTH = 5.5
GOAL_AREA_WIDTH = 18.32
CENTER_CIRCLE_RADIUS = 9.15
POINT_RADIUS = 0.5
PENALTY_SPOT_DIST = 11



# ===== Base values (unscaled) =====
PLAYER_OUTER_RADIUS_BASE = 1.6  # reference value when scale = 1.0
 
# The following values become properties depending on the scale
class DynamicConfig:
    """Holds dynamic, scale-dependent visual constants.

    The `scale` property controls derived sizes (player radii, arrow widths,
    trajectory line widths, etc.). Set `CONFIG.scale` to adjust the UI scale
    globally without touching call sites.
    """
    
    _instance = None
    _scale = 1.0
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DynamicConfig, cls).__new__(cls)
        return cls._instance
    
    @property
    def scale(self):
        return self._scale
    
    @scale.setter
    def scale(self, value):
        self._scale = max(0.5, min(2.0, value))
    
    @property
    def PLAYER_OUTER_RADIUS(self):
        return PLAYER_OUTER_RADIUS_BASE * self._scale
    
    @property
    def PLAYER_INNER_RADIUS(self):
        return 3/4 * self.PLAYER_OUTER_RADIUS
    
    @property
    def PLAYER_ARROW_THICKNESS(self):
        return 1/4 * self.PLAYER_OUTER_RADIUS
    
    @property
    def PLAYER_CHEVRON_SIZE(self):
        return 1/2 * self.PLAYER_OUTER_RADIUS
    
    @property
    def BALL_RADIUS(self):
        return 7/16 * self.PLAYER_OUTER_RADIUS
    
    @property
    def TACTICAL_ARROW_DETECTION_RADIUS(self):
        return self.PLAYER_OUTER_RADIUS
    
    @property
    def TRAJECTORY_PLAYER_LINE_WIDTH(self):
        return 3/16 * self.PLAYER_OUTER_RADIUS

    @property
    def TRAJECTORY_BALL_LINE_WIDTH(self):
        return 5/16 * self.PLAYER_OUTER_RADIUS

    @property
    def OFFSIDE_LINE_WIDTH(self):
        return 5/16 * self.PLAYER_OUTER_RADIUS

# Global instance
CONFIG = DynamicConfig()

# For compatibility with existing code, provide function accessors
def get_player_outer_radius():
    return CONFIG.PLAYER_OUTER_RADIUS

def get_player_inner_radius():
    return CONFIG.PLAYER_INNER_RADIUS

def get_player_arrow_thickness():
    return CONFIG.PLAYER_ARROW_THICKNESS

def get_player_chevron_size():
    return CONFIG.PLAYER_CHEVRON_SIZE

def get_ball_radius():
    return CONFIG.BALL_RADIUS

def get_tactical_arrow_detection_radius():
    return CONFIG.TACTICAL_ARROW_DETECTION_RADIUS

def get_trajectory_player_line_width():
    return CONFIG.TRAJECTORY_PLAYER_LINE_WIDTH

def get_trajectory_ball_line_width():
    return CONFIG.TRAJECTORY_BALL_LINE_WIDTH

def get_offside_line_width():
    return CONFIG.OFFSIDE_LINE_WIDTH

# Static values (do not change with scale)
PLAYER_ROTATION_OFFSET_DEG = 270
PLAYER_ROTATION_DEFAULT_DEG = 90
PLAYER_CHEVRON_ANGLE_DEG = 150
VELOCITY_ARROW_SCALE = 1
BALL_COLOR = "#FFA500"

# Annotation_tools constants
ANNOTATION_ARROW_HEAD_LENGTH = 2
ANNOTATION_ARROW_HEAD_ANGLE = 30
ANNOTATION_ARROW_BASE_WIDTH_VALUE = 1
ANNOTATION_ARROW_SCALE_RANGE = (ANNOTATION_ARROW_BASE_WIDTH_VALUE, ANNOTATION_ARROW_BASE_WIDTH_VALUE * 10)

# ---- Timeline and UI ----
MAX_TIMELINE_WIDTH = 550
MIN_TIMELINE_WIDTH = 350
EXTRA_TIMELINE_PADDING = 60
TIMELINE_SLIDER_HEIGHT = 24
TIMELINE_GROOVE_HEIGHT = TIMELINE_SLIDER_HEIGHT - TIMELINE_SLIDER_HEIGHT//3
TIMELINE_HANDLE_WIDTH = TIMELINE_GROOVE_HEIGHT // 2
TIMELINE_HANDLE_HEIGHT = TIMELINE_GROOVE_HEIGHT + TIMELINE_GROOVE_HEIGHT//2
NAV_BUTTON_WIDTH = 35
NAV_BUTTON_HEIGHT = 30

# time
FPS = 25
LENGTH_FIRST_HALF = 45
LENGTH_SECOND_HALF = 45
LENGTH_OVERTIME_HALF = 15
LENGTH_FULL_TIME = LENGTH_FIRST_HALF + LENGTH_SECOND_HALF
LENGTH_EXTRA_TIME = 2 * LENGTH_OVERTIME_HALF

# Players and ball trajectories
TRAJECTORY_STYLE = Qt.PenStyle.DotLine
TRAJECTORY_SAMPLE_RATE = 5
TRAJECTORY_FADING = True  # Set to False to disable progressive fading of trajectories

# Simulation preview mode: when True, only display user-drawn arrows (team-colored)
# without computing or drawing simulated/future trajectories
SIMULATION_ONLY_ARROWS = True