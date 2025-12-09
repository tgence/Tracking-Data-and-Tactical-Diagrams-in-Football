# zone_properties.py
"""
Properties panels for tactical zones.

Provides UI controls for modifying zone properties including color, width,
transparency, and rotation.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, 
    QPushButton, QColorDialog, QSpinBox, QGroupBox, QGridLayout,
    QComboBox, QDoubleSpinBox, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor, QIcon
import os
from config import *
from annotation.annotation import ConeZoneItem

# ColorButton class for zone properties
class ColorButton(QPushButton):
    """A button that displays a color and opens a color dialog when clicked.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    """
    
    colorChanged = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 30)
        self.current_color = "#000000"
        self.clicked.connect(self._on_clicked)
        self._update_appearance()
        
    def _on_clicked(self):
        """Open color dialog and emit signal if color changes."""
        color = QColorDialog.getColor(QColor(self.current_color), self)
        if color.isValid():
            new_color = color.name()
            if new_color != self.current_color:
                self.current_color = new_color
                self._update_appearance()
                self.colorChanged.emit(new_color)
                
    def _update_appearance(self):
        """Update button appearance to show current color."""
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.current_color};
                border: 2px solid #333333;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border: 2px solid #666666;
            }}
        """)
        
    def update_color(self, color):
        """Update the displayed color without opening dialog."""
        self.current_color = color
        self._update_appearance()


class ZoneProperties(QWidget):
    """Properties panel for tactical zones with color/width/transparency/rotation.

    Signals
    -------
    colorChanged : (str)
    widthChanged : (int)
    styleChanged : (str)
    fillAlphaChanged : (int)
    rotationChanged : (float)
    deleteRequested : ()
    propertiesConfirmed : ()
    """
    
    # Signals
    colorChanged = pyqtSignal(str)
    widthChanged = pyqtSignal(int)
    styleChanged = pyqtSignal(str)
    fillAlphaChanged = pyqtSignal(int)
    rotationChanged = pyqtSignal(float)
    deleteRequested = pyqtSignal()
    propertiesConfirmed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.Window)
        self.setWindowTitle("Zone Properties")
        self.current_zone = None
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)  # More margin around the whole dialog
        layout.setSpacing(10)  # Much more spacing between sections
        
        # Title
        title = QLabel("Zone Properties")
        title.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 5px;")
        layout.addWidget(title)
        
        # === Color and Style Group ===
        style_group = QGroupBox("Appearance")
        style_layout = QVBoxLayout()
        style_layout.setSpacing(20)  # More spacing between items
        style_layout.setContentsMargins(15, 15, 15, 15)  # More space inside the group
        
        # Color
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        self.color_btn = ColorButton()
        self.color_btn.colorChanged.connect(self._on_color_changed)
        color_layout.addWidget(self.color_btn)
        color_layout.addStretch()
        style_layout.addLayout(color_layout)
        
        # Width
        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 5)
        self.width_spin.setValue(1)
        self.width_spin.setFixedSize(80, 20)  # Wider width box
        self.width_spin.valueChanged.connect(self._on_width_changed)
        width_layout.addWidget(self.width_spin)
        width_layout.addStretch()
        style_layout.addLayout(width_layout)
        
        # Line style
        line_style_layout = QHBoxLayout()
        line_style_layout.addWidget(QLabel("Line Style:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems(["Solid", "Dashed"])
        self.style_combo.setFixedSize(120, 20)  # Wider and taller line style box
        self.style_combo.currentIndexChanged.connect(self._on_style_changed)
        line_style_layout.addWidget(self.style_combo)
        line_style_layout.addStretch()
        style_layout.addLayout(line_style_layout)

        # Fill transparency
        alpha_layout = QHBoxLayout()
        alpha_layout.addWidget(QLabel("Opacity:"))
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(0, 255)
        self.alpha_slider.setValue(0)
        self.alpha_slider.valueChanged.connect(self._on_alpha_changed)
        alpha_layout.addWidget(self.alpha_slider)
        
        self.alpha_label = QLabel("0")
        self.alpha_label.setFixedWidth(30)
        alpha_layout.addWidget(self.alpha_label)
        alpha_layout.addStretch()
        style_layout.addLayout(alpha_layout)
        
        style_group.setLayout(style_layout)
        layout.addWidget(style_group, 2)  # Give Appearance more space (stretch factor 2)
        
        # === Rotation Group ===
        rotation_group = QGroupBox("Rotation")
        rotation_layout = QHBoxLayout()
        rotation_layout.setContentsMargins(15, 5, 15, 5)  # Compact vertical margins
        
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-180, 180)
        self.rotation_spin.setSuffix("°")
        self.rotation_spin.setDecimals(1)
        self.rotation_spin.setValue(0)
        self.rotation_spin.setFixedWidth(80)  # Reduce width of spin box
        self.rotation_spin.valueChanged.connect(self._on_rotation_changed)
        rotation_layout.addWidget(self.rotation_spin)
        
        # Reset rotation button (bigger)
        reset_rotation_btn = QPushButton("Reset")
        reset_rotation_btn.setFixedSize(80, 30)  # Bigger button
        reset_rotation_btn.clicked.connect(self._on_reset_rotation)
        rotation_layout.addWidget(reset_rotation_btn)
        
        rotation_group.setLayout(rotation_layout)
        layout.addWidget(rotation_group, 0)  # Give Rotation minimal space (stretch factor 0)
        
        # === Control Buttons (same style as ArrowProperties) ===
        buttons_frame = QFrame()
        buttons_frame.setStyleSheet("background-color: #2b2b2b; border-top: 1px solid #555;")
        buttons_layout = QHBoxLayout(buttons_frame)
        buttons_layout.setContentsMargins(12, 8, 12, 8)
        buttons_layout.setSpacing(8)
        
        # Undo
        self.undo_button = QPushButton()
        self.undo_button.setFixedSize(40, 30)
        self.undo_button.setToolTip("Undo last action")
        undo_icon_path = os.path.join(SVG_DIR, "undo.svg")
        if os.path.exists(undo_icon_path):
            self.undo_button.setIcon(QIcon(undo_icon_path))
        buttons_layout.addWidget(self.undo_button)
        
        # Redo  
        self.redo_button = QPushButton()
        self.redo_button.setFixedSize(40, 30)
        self.redo_button.setToolTip("Redo last action")
        redo_icon_path = os.path.join(SVG_DIR, "redo.svg")
        if os.path.exists(redo_icon_path):
            self.redo_button.setIcon(QIcon(redo_icon_path))
        buttons_layout.addWidget(self.redo_button)
        
        buttons_layout.addStretch()
        
        # OK Button
        ok_btn = QPushButton("OK")
        ok_btn.setFixedSize(80, 30)
        ok_btn.clicked.connect(self.propertiesConfirmed.emit)
        buttons_layout.addWidget(ok_btn)
        
        # Delete Button (red with white text)
        delete_btn = QPushButton("Delete")
        delete_btn.setFixedSize(80, 30)
        delete_btn.setStyleSheet("background-color: #ff4444; color: white; border: 2px solid #ff4444;")
        delete_btn.clicked.connect(self.deleteRequested.emit)
        buttons_layout.addWidget(delete_btn)
        
        layout.addWidget(buttons_frame)
        
        # Set fixed size - taller to accommodate more spacing
        self.setFixedSize(340, 450)
        
        # Initial state
        self.setEnabled(False)
        
    def set_zone(self, zone):
        """Set the zone to edit.

        Parameters
        ----------
        zone : RectangleZoneItem | EllipseZoneItem | None
            Zone item to edit, or None to disable the panel.
        """
        self.current_zone = zone
        if zone:
            self.setEnabled(True)
            self._load_zone_properties()
        else:
            self.setEnabled(False)
            
    def _load_zone_properties(self):
        """Load properties from the current zone into the widgets."""
        if not self.current_zone:
            return
            
        # Color
        self.color_btn.update_color(self.current_zone.zone_color)
        
        # Width
        self.width_spin.setValue(self.current_zone.zone_width)
        
        # Fill alpha
        alpha = self.current_zone.zone_fill_alpha
        self.alpha_slider.setValue(alpha)
        self.alpha_label.setText(str(alpha))
        
        # Rotation
        rotation = self.current_zone.get_rotation()
        self.rotation_spin.setValue(rotation)
        
        # Style
        current_style = getattr(self.current_zone, 'zone_style', 'solid')
        self.style_combo.setCurrentIndex(1 if current_style == 'dashed' else 0)
        
    def _on_color_changed(self, color):
        """Handle color change and update the current zone if any."""
        if self.current_zone:
            self.current_zone.set_color(color)
        self.colorChanged.emit(color)
        
    def _on_width_changed(self, width):
        """Handle width change and update the current zone if any."""
        if self.current_zone:
            self.current_zone.set_width(width)
        self.widthChanged.emit(width)
    
    def _on_style_changed(self):
        """Handle line style change and update the current zone if any."""
        style_text = self.style_combo.currentText().lower()
        normalized = 'dashed' if 'dash' in style_text else 'solid'
        if self.current_zone:
            # Call zone item method directly; managers also expose set_style when used programmatically
            if hasattr(self.current_zone, 'set_style'):
                self.current_zone.set_style(normalized)
        self.styleChanged.emit(normalized)
        
    def _on_alpha_changed(self, alpha):
        """Handle fill alpha change and update the current zone if any."""
        self.alpha_label.setText(str(alpha))
        if self.current_zone:
            self.current_zone.set_fill_alpha(alpha)
        self.fillAlphaChanged.emit(alpha)
        
    def _on_rotation_changed(self, angle):
        """Handle rotation change and update the current zone if any."""
        if self.current_zone:
            self.current_zone.set_rotation(angle)
        self.rotationChanged.emit(angle)
        
    def _on_reset_rotation(self):
        """Reset rotation to 0 degrees."""
        self.rotation_spin.setValue(0)
        
    def show_for_zone(self, zone, pos):
        """Show the properties panel for a specific zone at the given position.

        Parameters
        ----------
        zone : RectangleZoneItem | EllipseZoneItem
        pos : QPoint
            Screen position for the popup.
        """
        self.set_zone(zone)
        self.move(pos)
        self.show()
        self.raise_()
        self.activateWindow()




class ConeZoneProperties(QWidget):
    """Properties panel for Cone zones (same UI as ZoneProperties + interior angle).

    Signals
    -------
    colorChanged : (str)
    widthChanged : (int)
    styleChanged : (str)
    fillAlphaChanged : (int)
    rotationChanged : (float)
    spreadChanged : (float)
    deleteRequested : ()
    propertiesConfirmed : ()
    """

    # mêmes signaux que ZoneProperties + spreadChanged
    colorChanged = pyqtSignal(str)
    widthChanged = pyqtSignal(int)
    styleChanged = pyqtSignal(str)
    fillAlphaChanged = pyqtSignal(int)
    rotationChanged = pyqtSignal(float)
    spreadChanged = pyqtSignal(float)
    deleteRequested = pyqtSignal()
    propertiesConfirmed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.Window)
        self.setWindowTitle("Cone Properties")
        self.current_zone = None
        self._setup_ui()

    # ===== UI : copie de ZoneProperties + champ Angle =====
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("Cone Properties")
        title.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 5px;")
        layout.addWidget(title)

        # === Appearance (identique) ===
        style_group = QGroupBox("Appearance")
        style_layout = QVBoxLayout()
        style_layout.setSpacing(20)
        style_layout.setContentsMargins(15, 15, 15, 15)

        # Color
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        # ColorButton est déjà utilisé par ZoneProperties
        self.color_btn = ColorButton()
        self.color_btn.colorChanged.connect(self._on_color_changed)
        color_layout.addWidget(self.color_btn)
        color_layout.addStretch()
        style_layout.addLayout(color_layout)

        # Width
        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 5)
        self.width_spin.setValue(1)
        self.width_spin.setFixedSize(80, 20)
        self.width_spin.valueChanged.connect(self._on_width_changed)
        width_layout.addWidget(self.width_spin)
        width_layout.addStretch()
        style_layout.addLayout(width_layout)

        # Line style
        line_style_layout = QHBoxLayout()
        line_style_layout.addWidget(QLabel("Line Style:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems(["Solid", "Dashed"])
        self.style_combo.setFixedSize(120, 20)
        self.style_combo.currentIndexChanged.connect(self._on_style_changed)
        line_style_layout.addWidget(self.style_combo)
        line_style_layout.addStretch()
        style_layout.addLayout(line_style_layout)

        # Fill transparency
        alpha_layout = QHBoxLayout()
        alpha_layout.addWidget(QLabel("Opacity:"))
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(0, 255)
        self.alpha_slider.setValue(0)
        self.alpha_slider.valueChanged.connect(self._on_alpha_changed)
        alpha_layout.addWidget(self.alpha_slider)

        self.alpha_label = QLabel("0")
        self.alpha_label.setFixedWidth(30)
        alpha_layout.addWidget(self.alpha_label)
        alpha_layout.addStretch()
        style_layout.addLayout(alpha_layout)

        style_group.setLayout(style_layout)
        layout.addWidget(style_group, 2)

        # === Rotation (identique) + Interior angle (nouveau) ===
        rotation_group = QGroupBox("Rotation")
        rotation_layout = QHBoxLayout()
        rotation_layout.setContentsMargins(15, 5, 15, 5)

        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-180, 180)
        self.rotation_spin.setSuffix("°")
        self.rotation_spin.setDecimals(1)
        self.rotation_spin.setValue(0)
        self.rotation_spin.setFixedWidth(80)
        self.rotation_spin.valueChanged.connect(self._on_rotation_changed)
        rotation_layout.addWidget(self.rotation_spin)

        reset_rotation_btn = QPushButton("Reset")
        reset_rotation_btn.setFixedSize(80, 30)
        reset_rotation_btn.clicked.connect(self._on_reset_rotation)
        rotation_layout.addWidget(reset_rotation_btn)

        # ---- interior angle control (ajouté) ----
        rotation_layout.addSpacing(12)
        rotation_layout.addWidget(QLabel("Interior angle:"))
        self.spread_spin = QDoubleSpinBox()
        self.spread_spin.setRange(0.0, 360.0)          # permet >180 si besoin
        self.spread_spin.setDecimals(1)
        self.spread_spin.setSuffix("°")
        self.spread_spin.setValue(60.0)
        self.spread_spin.setFixedWidth(90)
        self.spread_spin.valueChanged.connect(self._on_spread_changed)
        rotation_layout.addWidget(self.spread_spin)

        rotation_group.setLayout(rotation_layout)
        layout.addWidget(rotation_group, 0)

        # === Buttons (identique) ===
        buttons_frame = QFrame()
        buttons_frame.setStyleSheet("background-color: #2b2b2b; border-top: 1px solid #555;")
        buttons_layout = QHBoxLayout(buttons_frame)
        buttons_layout.setContentsMargins(12, 8, 12, 8)
        buttons_layout.setSpacing(8)

        self.undo_button = QPushButton()
        self.undo_button.setFixedSize(40, 30)
        self.undo_button.setToolTip("Undo last action")
        undo_icon_path = os.path.join(SVG_DIR, "undo.svg")
        if os.path.exists(undo_icon_path):
            self.undo_button.setIcon(QIcon(undo_icon_path))
        buttons_layout.addWidget(self.undo_button)

        self.redo_button = QPushButton()
        self.redo_button.setFixedSize(40, 30)
        self.redo_button.setToolTip("Redo last action")
        redo_icon_path = os.path.join(SVG_DIR, "redo.svg")
        if os.path.exists(redo_icon_path):
            self.redo_button.setIcon(QIcon(redo_icon_path))
        buttons_layout.addWidget(self.redo_button)

        buttons_layout.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setFixedSize(80, 30)
        ok_btn.clicked.connect(self.propertiesConfirmed.emit)
        buttons_layout.addWidget(ok_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setFixedSize(80, 30)
        delete_btn.setStyleSheet("background-color: #ff4444; color: white; border: 2px solid #ff4444;")
        delete_btn.clicked.connect(self.deleteRequested.emit)
        buttons_layout.addWidget(delete_btn)

        layout.addWidget(buttons_frame)

        self.setFixedSize(340, 450)
        self.setEnabled(False)




    def set_zone(self, zone):
        """Set the zone to edit.

        Parameters
        ----------
        zone : RectangleZoneItem | EllipseZoneItem | None
            Zone item to edit, or None to disable the panel.
        """
        self.current_zone = zone
        if zone:
            self.setEnabled(True)
            self._load_zone_properties()
        else:
            self.setEnabled(False)
            
    def _load_zone_properties(self):
        """Load properties from the current zone into the widgets."""
        if not self.current_zone:
            return
            
        # Color
        self.color_btn.update_color(self.current_zone.zone_color)
        
        # Width
        self.width_spin.setValue(self.current_zone.zone_width)
        
        # Fill alpha
        alpha = self.current_zone.zone_fill_alpha
        self.alpha_slider.setValue(alpha)
        self.alpha_label.setText(str(alpha))
        
        # Rotation
        rotation = self.current_zone.get_rotation()
        self.rotation_spin.setValue(rotation)
        
        # Style
        current_style = getattr(self.current_zone, 'zone_style', 'solid')
        self.style_combo.setCurrentIndex(1 if current_style == 'dashed' else 0)
        
    def _on_color_changed(self, color):
        """Handle color change and update the current zone if any."""
        if self.current_zone:
            self.current_zone.set_color(color)
        self.colorChanged.emit(color)
        
    def _on_width_changed(self, width):
        """Handle width change and update the current zone if any."""
        if self.current_zone:
            self.current_zone.set_width(width)
        self.widthChanged.emit(width)
    
    def _on_style_changed(self):
        """Handle line style change and update the current zone if any."""
        style_text = self.style_combo.currentText().lower()
        normalized = 'dashed' if 'dash' in style_text else 'solid'
        if self.current_zone:
            # Call zone item method directly; managers also expose set_style when used programmatically
            if hasattr(self.current_zone, 'set_style'):
                self.current_zone.set_style(normalized)
        self.styleChanged.emit(normalized)
        
    def _on_alpha_changed(self, alpha):
        """Handle fill alpha change and update the current zone if any."""
        self.alpha_label.setText(str(alpha))
        if self.current_zone:
            self.current_zone.set_fill_alpha(alpha)
        self.fillAlphaChanged.emit(alpha)
        
    def _on_rotation_changed(self, angle):
        """Handle rotation change and update the current zone if any."""
        if self.current_zone:
            self.current_zone.set_rotation(angle)
        self.rotationChanged.emit(angle)
        
    def _on_spread_changed(self, value: float):
        if self.current_zone and hasattr(self.current_zone, "set_spread_deg"):
            self.current_zone.set_spread_deg(float(value))
        self.spreadChanged.emit(float(value))

    def _on_reset_rotation(self):
        """Reset rotation to 0 degrees."""
        self.rotation_spin.setValue(0)
        
    def show_for_zone(self, zone, pos):
        """Show the properties panel for a specific zone at the given position.

        Parameters
        ----------
        zone : RectangleZoneItem | EllipseZoneItem
        pos : QPoint
            Screen position for the popup.
        """
        self.set_zone(zone)
        self.move(pos)
        self.show()
        self.raise_()
        self.activateWindow()