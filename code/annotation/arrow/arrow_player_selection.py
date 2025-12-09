# arrow_player_selection.py
"""
Player selection dialog for associating arrows to players.

Provides circular player buttons styled like the pitch representation and a
dialog that lists Home and Away players for quick selection.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFrame, QGridLayout
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPainterPath
from config import *

class PlayerCircleButton(QPushButton):
    """Circular player button visually matching pitch player design."""
    def __init__(self, player_id, player_number, main_color, sec_color, num_color, parent=None):
        super().__init__(parent)
        self.player_id = player_id
        self.player_number = str(player_number)
        self.main_color = QColor(main_color)
        self.sec_color = QColor(sec_color)
        self.num_color = QColor(num_color)
        self.is_selected = False
        
        self.setFixedSize(50, 50)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 25px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Circle parameters (mirrors pitch_widget style)
        center_x, center_y = 25, 25
        outer_radius = 20
        inner_radius = 15
        
        # Top half-circle (main color)
        painter.setBrush(QBrush(self.main_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPie(center_x - outer_radius, center_y - outer_radius, 
                       outer_radius * 2, outer_radius * 2, 0, 180 * 16)
        
        # Bottom half-circle (secondary color)
        painter.setBrush(QBrush(self.sec_color))
        painter.drawPie(center_x - outer_radius, center_y - outer_radius,
                       outer_radius * 2, outer_radius * 2, 180 * 16, 180 * 16)
        
        # Inner circle (main color)
        painter.setBrush(QBrush(self.main_color))
        painter.drawEllipse(center_x - inner_radius, center_y - inner_radius,
                          inner_radius * 2, inner_radius * 2)
        
        # Selection ring if selected
        if self.is_selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#39C6FF"), 2))  # light blue, width 2
            painter.drawEllipse(center_x - outer_radius - 2, center_y - outer_radius - 2, 
                            (outer_radius + 2) * 2, (outer_radius + 2) * 2)

        
        # Player number
        painter.setPen(QPen(self.num_color))
        font = QFont("Arial", 12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.player_number)
    
    def set_selected(self, selected):
        """Update selection state"""
        self.is_selected = selected
        self.update()

class ArrowPlayerSelection(QDialog):
    """Dialog to pick a player (Home/Away) with pitch-like visuals."""
    playerSelected = pyqtSignal(str, str)  # player_id, player_text
    
    def __init__(self, home_players, away_players, title="Select Player", parent=None, default_selected_id=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        
        self.home_players = home_players
        self.away_players = away_players
        self.selected_player_id = None
        self.selected_player_text = None
        self.player_buttons = []
        self.default_selected_id = default_selected_id
        
        # Grab team colors for labels
        self.home_main_color = "#4CAF50"  # default green
        self.away_main_color = "#F44336"  # default red
        
        if home_players:
            first_home_player = next(iter(home_players.values()))
            self.home_main_color = first_home_player[1]  # main_color
        
        if away_players:
            first_away_player = next(iter(away_players.values()))
            self.away_main_color = first_away_player[1]  # main_color
        
        self._setup_ui()
        # Apply default selection if provided
        if self.default_selected_id:
            self._preselect_default(self.default_selected_id)
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Dialog style
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                border: 2px solid #555;
                border-radius: 10px;
            }
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 14px;
                text-align: center;
            }
            QPushButton {
                background-color: #404040;
                color: white;
                border: 1px solid #666;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
                border-color: #888;
            }
            QPushButton:pressed {
                background-color: #353535;
            }
        """)
        
        # Titre
        title_label = QLabel("Select a Player")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Teams container
        teams_layout = QHBoxLayout()
        teams_layout.setSpacing(30)
        
        # Home team
        home_frame = QFrame()
        home_layout = QVBoxLayout(home_frame)
        home_layout.setSpacing(10)
        
        home_label = QLabel("Home")
        home_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        home_label.setStyleSheet(f"color: {self.home_main_color}; font-size: 16px; font-weight: bold;")
        home_layout.addWidget(home_label)
        
        # Grid for Home players
        home_grid = QGridLayout()
        home_grid.setSpacing(8)
        
        row, col = 0, 0
        for player_id, (number, main_color, sec_color, num_color) in self.home_players.items():
            btn = PlayerCircleButton(player_id, number, main_color, sec_color, num_color)
            btn.clicked.connect(lambda checked, pid=player_id, num=number: 
                              self._select_player(pid, f"Player {num}"))
            home_grid.addWidget(btn, row, col)
            self.player_buttons.append(btn)
            col += 1
            if col >= 4:  # 4 players per line
                col = 0
                row += 1
        
        home_layout.addLayout(home_grid)
        teams_layout.addWidget(home_frame)
        
        # Vertical separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet("color: #666;")
        teams_layout.addWidget(separator)
        
        # Away team
        away_frame = QFrame()
        away_layout = QVBoxLayout(away_frame)
        away_layout.setSpacing(10)
        
        away_label = QLabel("Away")
        away_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        away_label.setStyleSheet(f"color: {self.away_main_color}; font-size: 16px; font-weight: bold;")
        away_layout.addWidget(away_label)
        
        # Grid for Away players
        away_grid = QGridLayout()
        away_grid.setSpacing(8)
        
        row, col = 0, 0
        for player_id, (number, main_color, sec_color, num_color) in self.away_players.items():
            btn = PlayerCircleButton(player_id, number, main_color, sec_color, num_color)
            btn.clicked.connect(lambda checked, pid=player_id, num=number: 
                              self._select_player(pid, f"Player {num}"))
            away_grid.addWidget(btn, row, col)
            self.player_buttons.append(btn)
            col += 1
            if col >= 4:  # 4 players per line
                col = 0
                row += 1
        
        away_layout.addLayout(away_grid)
        teams_layout.addWidget(away_frame)
        
        layout.addLayout(teams_layout)
        
        # OK/Cancel buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #757575;
            }
            QPushButton:hover {
                background-color: #9E9E9E;
            }
        """)
        
        # "No Player" button to allow clearing the association
        no_player_button = QPushButton("No Player")
        no_player_button.clicked.connect(self._select_no_player)
        no_player_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FFB74D;
            }
        """)
        
        self.ok_button = QPushButton("OK")
        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #66BB6A;
            }
            QPushButton:disabled {
                background-color: #666;
                color: #999;
            }
        """)
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(cancel_button)
        buttons_layout.addWidget(no_player_button)
        buttons_layout.addWidget(self.ok_button)
        
        layout.addLayout(buttons_layout)
        
        # Fixed size
        self.setFixedSize(600, 450)
    
    def _preselect_default(self, player_id):
        """Preselect a player by id and enable OK."""
        # Determine display text (number)
        number_text = None
        if player_id in self.home_players:
            number_text = self.home_players[player_id][0]
        elif player_id in self.away_players:
            number_text = self.away_players[player_id][0]
        if number_text is None:
            number_text = "?"
        
        self.selected_player_id = player_id
        self.selected_player_text = f"Player {number_text}"
        # Refresh buttons selection rings
        for btn in self.player_buttons:
            btn.set_selected(btn.player_id == player_id)
        # Enable OK
        if hasattr(self, 'ok_button') and self.ok_button is not None:
            self.ok_button.setEnabled(True)
    
    def _select_player(self, player_id, player_text):
        """Select a player"""
        self.selected_player_id = player_id
        self.selected_player_text = player_text
        self.ok_button.setEnabled(True)
        
        # Refresh selected ring across all buttons
        for btn in self.player_buttons:
            btn.set_selected(btn.player_id == player_id)
    
    def _select_no_player(self):
        """Select no player"""
        self.selected_player_id = None
        self.selected_player_text = "No Player"
        
        # Clear all selection rings
        for btn in self.player_buttons:
            btn.set_selected(False)
        
        # Close the dialog immediately
        self.accept()
    
    def accept(self):
        """Accept the selection"""
        if self.selected_player_id is not None or self.selected_player_text == "No Player":
            self.playerSelected.emit(self.selected_player_id or "", self.selected_player_text or "")
        super().accept()
    
    @staticmethod
    def select_player(home_players, away_players, title="Select Player", parent=None):
        """Static method to select a player"""
        dialog = PlayerSelectionDialog(home_players, away_players, title, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_player_id, dialog.selected_player_text
        return None, None