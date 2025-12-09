# annotation.py
"""
Annotation management on the pitch scene.

Supports arrows, rectangles, and ellipses with selection/move and visual property updates.
Used by tactical simulation to associate annotations with players and action types.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPen, QColor, QPainterPath, QBrush, QTransform, QCursor
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsItemGroup, QGraphicsRectItem, QGraphicsEllipseItem, QStyleOptionGraphicsItem, QStyle, QGraphicsItem

import math

from config import *
DEFAULT_ARROW_COLOR = "#000000"
DEFAULT_ZONE_COLOR = "#000000"
DEFAULT_ZONE_WIDTH = 1
DEFAULT_ZONE_ALPHA = 0  # transparency for fill (0 = transparent)

# Resize handle constants
HANDLE_SIZE = 1  # Size of corner handles in pixels


class ResizeHandle(QGraphicsRectItem):
    """Small square handle for resizing objects at corners.

    Parameters
    ----------
    corner_type : {'top_left','top_right','bottom_left','bottom_right'}
        Which corner this handle controls.
    parent_item : QGraphicsItemGroup
        Parent item owning the selection rectangle.
    color : str, default '#000000'
        Handle color.
    """
    
    def __init__(self, corner_type, parent_item, color="#000000"):
        super().__init__()
        self.corner_type = corner_type  # 'top_left', 'top_right', 'bottom_left', 'bottom_right'
        self.parent_item = parent_item
        self.handle_color = color
        self._dragging = False
        self._last_pos = None
        
        # Set handle size centered on (0,0) so its center aligns with the target corner
        self.setRect(-HANDLE_SIZE / 2.0, -HANDLE_SIZE / 2.0, HANDLE_SIZE, HANDLE_SIZE)
        self.setPen(QPen(QColor(color), 0.1))
        self.setBrush(QBrush(QColor(color)))
        self.setZValue(1001)  # Above selection rectangle

        # Set cursor based on corner type
        cursor_map = {
            'top_left': Qt.CursorShape.SizeFDiagCursor,
            'top_right': Qt.CursorShape.SizeBDiagCursor,
            'bottom_left': Qt.CursorShape.SizeBDiagCursor,
            'bottom_right': Qt.CursorShape.SizeFDiagCursor
        }
        self.setCursor(cursor_map.get(corner_type, Qt.CursorShape.SizeFDiagCursor))
        
        # Enable mouse interaction but disable automatic movement
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)
        
        # Make sure handle receives mouse events first
        self.setZValue(1002)  # Above everything else
        
    def mousePressEvent(self, event):
        """Handle mouse press for resize operation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            # Handles are in scene, so use scene coordinates directly
            scene_pos = event.scenePos()
            self._last_pos = scene_pos
            self.parent_item.start_resize(self.corner_type, scene_pos)
            event.accept()
        else:
            super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        """Handle mouse move for resize operation."""
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            # Handles are in scene, so use scene coordinates directly
            scene_pos = event.scenePos()
            self.parent_item.update_resize(self.corner_type, scene_pos)
            self._last_pos = scene_pos
            event.accept()
        else:
            super().mouseMoveEvent(event)
        
    def mouseReleaseEvent(self, event):
        """Handle mouse release to end resize operation."""
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.parent_item.end_resize()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

class ArrowAnnotationManager:
    def __init__(self, scene):
        """Manage creation, preview, selection, and storage of arrow items.

        Parameters
        ----------
        scene : QGraphicsScene
            Scene where arrows are created/managed.
        """
        self.scene = scene
        self.arrows = []
        self.arrow_points = []
        self.arrow_color = DEFAULT_ARROW_COLOR
        self.arrow_width = ANNOTATION_ARROW_BASE_WIDTH_VALUE
        self.arrow_style = "solid"
        self.arrow_curved = False
        self.arrow_preview = None
        self.selected_arrow = None
        self.current_mode = "select"
        self.tactical_mode = False

    def set_tactical_mode(self, enabled):
        self.tactical_mode = enabled

    def add_point(self, pos):
        if not self.arrow_curved:
            if len(self.arrow_points) < 2:
                self.arrow_points.append(pos)
        else:
            self.arrow_points.append(pos)

    def set_mode(self, mode):
        self.arrow_curved = (mode == "curve")
        self.arrow_points = []
        self.remove_arrow_preview()
        self.clear_selection()
        self.current_mode = mode


    def clear_selection(self):        
        for arrow in list(self.arrows):
            try:
                arrow.setSelected(False)
            except RuntimeError:
                self.arrows.remove(arrow)
        self.selected_arrow = None

    def select_arrow(self, arrow):
        """Select a specific arrow and unselect others."""
        self.clear_selection()
        self.selected_arrow = arrow
        if arrow:
            arrow.setSelected(True)
            # Visually emphasize selection (rectangle handled by item)
    
    def set_color(self, color):
        if self.selected_arrow:
            self.selected_arrow.set_color(color)
        else:
            self.arrow_color = color

    def set_width(self, width):
        if self.selected_arrow:
            self.selected_arrow.set_width(width)
        else:
            self.arrow_width = width

    def set_style(self, style):
        if self.selected_arrow:
            self.selected_arrow.set_style(style)
        else:
            self.arrow_style = style


    def remove_arrow_preview(self):
        if self.arrow_preview:
            try:
                self.scene.removeItem(self.arrow_preview)
            except RuntimeError:
                pass
            self.arrow_preview = None

    def update_preview(self, pos):
        if not self.arrow_points:
            return
        if not self.arrow_curved:
            pts = [self.arrow_points[0], pos]
        else:
            pts = self.arrow_points + [pos]
        self.remove_arrow_preview()
        self.arrow_preview = self.draw_arrow(pts, preview=True)

    def finish_arrow(self):
        if len(self.arrow_points) < 2:
            self.arrow_points = []
            self.remove_arrow_preview()
            return None

        arrow_item = self.draw_arrow(self.arrow_points, preview=False)
        if arrow_item:
            self.arrows.append(arrow_item)
        self.arrow_points = []
        self.remove_arrow_preview()
        return arrow_item


    def try_finish_arrow(self):
        if len(self.arrow_points) >= 2:
            self.finish_arrow()
        else:
            self.cancel_arrow()

    def cancel_arrow(self):
        self.arrow_points = []
        self.remove_arrow_preview()


    def draw_arrow_head_triangle(self, start, end, width_scale=1.0, color=None):
        """Draw triangular arrowhead with specified color"""
        dx, dy = end.x() - start.x(), end.y() - start.y()
        angle = math.atan2(dy, dx)
        
        length = ANNOTATION_ARROW_HEAD_LENGTH * width_scale
        
        angle_rad = math.radians(ANNOTATION_ARROW_HEAD_ANGLE)
        angle1 = angle + angle_rad
        angle2 = angle - angle_rad
        
        p1 = QPointF(
            end.x() - length * math.cos(angle1),
            end.y() - length * math.sin(angle1)
        )
        p2 = QPointF(
            end.x() - length * math.cos(angle2),
            end.y() - length * math.sin(angle2)
        )
        
        path = QPainterPath()
        path.moveTo(end)
        path.lineTo(p1)
        path.lineTo(p2)
        path.closeSubpath()
        return path

    def draw_arrow(self, pts, preview=False):
        if len(pts) < 2:
            return None
        # Note: preview uses reduced alpha; geometry/styling is otherwise identical
        color = self.arrow_color
        width = self.arrow_width
        style = self.arrow_style
        if preview:
            # Add alpha for preview (e.g., 0.5 transparency)
            col = QColor(color)
            col.setAlphaF(0.5)
            color = col.name()  # PyQt6: no HexArgb enum; name() includes alpha if set
        arrow = CustomArrowItem(
            arrow_points=pts,
            color=color,
            width=width,
            style=style
        )
        arrow.setZValue(999 if not preview else 998)
        self.scene.addItem(arrow)
        return arrow


    def delete_last_arrow(self):
        """Delete the most recently created arrow from the scene and memory."""
        if self.arrows:
            arrow_item = self.arrows.pop()
            try:
                self.scene.removeItem(arrow_item)
            except RuntimeError:
                pass
        self.clear_selection()

class CustomArrowItem(QGraphicsItemGroup):
    """Composite arrow item with a thin selection rectangle overlay.

    Parameters
    ----------
    arrow_points : list[QPointF]
    color : str
    width : float
    style : {'solid','dotted','zigzag'}
    parent : QGraphicsItem | None
    """
    def __init__(self, arrow_points, color, width, style, parent=None):
        super().__init__(parent)
        self.arrow_points = list(arrow_points)
        self.arrow_color = color
        self.arrow_width = width
        self.arrow_style = style
        self.from_player = None
        self.to_player = None
        self.original_width = width
        self._body_item = None
        self._head_item = None
        self._selection_rect = None
        self._selected_state = False
        
        # Resize handles
        self._resize_handles = {}
        self._is_resizing = False
        self._resize_start_pos = None
        self._resize_corner = None
        self._original_points = None

        # Configuration flags
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        
        self._draw_items()
        self._create_selection_rect()

    def paint(self, painter, option, widget):
        """Override to remove default white square"""
        option_modified = QStyleOptionGraphicsItem(option)
        option_modified.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option_modified, widget)

    def _create_selection_rect(self):
        """Create selection rectangle with a thin outline."""
        min_x = min(p.x() for p in self.arrow_points)
        max_x = max(p.x() for p in self.arrow_points)
        min_y = min(p.y() for p in self.arrow_points)
        max_y = max(p.y() for p in self.arrow_points)
        
        rect_x = min_x 
        rect_y = min_y 
        rect_width = (max_x - min_x) 
        rect_height = (max_y - min_y) 
        
        self._selection_rect = QGraphicsRectItem(rect_x, rect_y, rect_width, rect_height)
        
        # Thin outline, using arrow color for the selection rectangle
        self._selection_rect.setPen(QPen(QColor(self.arrow_color), 0.1))  
        self._selection_rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))  # No fill
        self._selection_rect.setZValue(1000)
        self._selection_rect.setVisible(False)
        
        self.addToGroup(self._selection_rect)
        
        # Create resize handles
        self._create_resize_handles()

    def setSelected(self, selected):
        """Show/hide selection rectangle and handles."""
        self._selected_state = selected
        if self._selection_rect:
            self._selection_rect.setVisible(selected)
        
        # Show/hide resize handles
        if selected:
            for handle in self._resize_handles.values():
                if not handle.scene() and self.scene():
                    self.scene().addItem(handle)
                handle.setVisible(True)
            self._update_handles_position()
        else:
            for handle in self._resize_handles.values():
                handle.setVisible(False)

    def _create_resize_handles(self):
        """Create resize handles at the corners of the selection rectangle."""
        corner_types = ['top_left', 'top_right', 'bottom_left', 'bottom_right']
        
        for corner_type in corner_types:
            handle = ResizeHandle(corner_type, self, self.arrow_color)
            handle.setVisible(False)
            self._resize_handles[corner_type] = handle
    
    def _update_handles_position(self):
        """Update positions of resize handles based on selection rectangle."""
        if not self._selection_rect or not self._resize_handles:
            return
            
        # Get selection rectangle bounds in local coordinates
        rect = self._selection_rect.rect()
        
        # Convert to scene coordinates by adding the group's position
        group_pos = self.pos()
        
        handle_positions = {
            'top_left': QPointF(group_pos.x() + rect.left(), group_pos.y() + rect.top()),
            'top_right': QPointF(group_pos.x() + rect.right(), group_pos.y() + rect.top()),
            'bottom_left': QPointF(group_pos.x() + rect.left(), group_pos.y() + rect.bottom()),
            'bottom_right': QPointF(group_pos.x() + rect.right(), group_pos.y() + rect.bottom())
        }
        
        for corner_type, handle in self._resize_handles.items():
            if corner_type in handle_positions:
                handle.setPos(handle_positions[corner_type])
    
    def start_resize(self, corner_type, scene_pos):
        """Start resize operation."""
        self._is_resizing = True
        self._resize_corner = corner_type
        self._resize_start_pos = scene_pos
        
        # Store original points relative to current group position
        group_pos = self.pos()
        self._original_points = [QPointF(p.x() - group_pos.x(), p.y() - group_pos.y()) for p in self.arrow_points]
        
        # Disable normal movement during resize
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
    
    def update_resize(self, corner_type, scene_pos):
        """Update arrow points during an active resize operation."""
        if not self._is_resizing or not self._original_points:
            return
            
        # Calculate resize delta
        delta = scene_pos - self._resize_start_pos
        
        # Get original bounding rectangle
        orig_min_x = min(p.x() for p in self._original_points)
        orig_max_x = max(p.x() for p in self._original_points)
        orig_min_y = min(p.y() for p in self._original_points)
        orig_max_y = max(p.y() for p in self._original_points)
        
        orig_width = orig_max_x - orig_min_x
        orig_height = orig_max_y - orig_min_y
        
        # Calculate new bounds based on corner being dragged
        new_min_x, new_max_x = orig_min_x, orig_max_x
        new_min_y, new_max_y = orig_min_y, orig_max_y
        
        if corner_type in ['top_left', 'bottom_left']:
            new_min_x = orig_min_x + delta.x()
        if corner_type in ['top_right', 'bottom_right']:
            new_max_x = orig_max_x + delta.x()
        if corner_type in ['top_left', 'top_right']:
            new_min_y = orig_min_y + delta.y()
        if corner_type in ['bottom_left', 'bottom_right']:
            new_max_y = orig_max_y + delta.y()
        
        new_width = new_max_x - new_min_x
        new_height = new_max_y - new_min_y
        
        # Prevent negative dimensions (allow very small forms)
        if new_width <= 1 or new_height <= 1:
            return
            
        # Calculate scale factors
        scale_x = new_width / orig_width if orig_width > 0 else 1
        scale_y = new_height / orig_height if orig_height > 0 else 1
        
        # Transform all arrow points
        group_pos = self.pos()
        for i, orig_relative_point in enumerate(self._original_points):
            # Convert relative point to absolute for calculation
            orig_point = QPointF(orig_relative_point.x() + group_pos.x(), orig_relative_point.y() + group_pos.y())
            
            # Normalize to [0,1] range
            norm_x = (orig_relative_point.x() - orig_min_x) / orig_width if orig_width > 0 else 0
            norm_y = (orig_relative_point.y() - orig_min_y) / orig_height if orig_height > 0 else 0
            
            # Apply new bounds and convert back to absolute coordinates
            new_relative_x = new_min_x + norm_x * new_width
            new_relative_y = new_min_y + norm_y * new_height
            new_x = new_relative_x + group_pos.x()
            new_y = new_relative_y + group_pos.y()
            
            self.arrow_points[i] = QPointF(new_x, new_y)
        
        # Redraw arrow with new points
        self._draw_items_without_moving_rect()
        
        # Update selection rectangle bounds and handles
        self._update_selection_rect_bounds()
        self._update_handles_position()
    
    def end_resize(self):
        """End resize operation and re-enable movement."""
        self._is_resizing = False
        self._resize_corner = None
        self._resize_start_pos = None
        self._original_points = None
        
        # Re-enable normal movement
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
    
    def _update_selection_rect_bounds(self):
        """Update selection rectangle bounds based on current arrow points."""
        if not self.arrow_points:
            return
            
        # Convert arrow points to local coordinates (relative to group position)
        group_pos = self.pos()
        
        local_points = [QPointF(p.x() - group_pos.x(), p.y() - group_pos.y()) for p in self.arrow_points]
        
        min_x = min(p.x() for p in local_points)
        max_x = max(p.x() for p in local_points)
        min_y = min(p.y() for p in local_points)
        max_y = max(p.y() for p in local_points)
        

        
        self._selection_rect.setRect(min_x, min_y, max_x - min_x, max_y - min_y)

    def isSelected(self):
        return self._selected_state
    
    def cleanup_handles(self):
        """Clean up handles when arrow is deleted."""
        for handle in self._resize_handles.values():
            if handle.scene():
                handle.scene().removeItem(handle)
        self._resize_handles.clear()

    def itemChange(self, change, value):
        """Handle move operations only - resize is handled by handles."""
        from PyQt6.QtWidgets import QGraphicsItem
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.isSelected():
            # Don't move if we're in resize mode (handles are controlling the resize)
            if self._is_resizing:
                return self.pos()
                
            # Store old position before change
            old_pos = self.pos()
            new_pos = value  # This is the position Qt wants to move to
            delta = new_pos - old_pos
            
            # Update all arrow points DURING the move
            for i in range(len(self.arrow_points)):
                self.arrow_points[i] += delta
            
            # Redraw arrow with new points
            self._draw_items_without_moving_rect()
            
            # Update selection rectangle and handles DURING move (real-time)
            self._update_selection_rect_bounds()
            self._update_handles_position()
            
        return super().itemChange(change, value)

    def _draw_items_without_moving_rect(self):
        """Redraw only the arrow items, not the selection rectangle."""
        # Remove only arrow sub-items (keep selection rectangle)
        for item in [self._body_item, self._head_item]:
            if item is not None:
                try:
                    self.removeFromGroup(item)
                    item.setParentItem(None)
                except Exception:
                    pass

        if len(self.arrow_points) < 2:
            return

        # Redraw the arrow
        self._draw_arrow_components()

    def _draw_items(self):
        """Draw arrow components and update selection rectangle."""
        # Remove previous arrow sub-items
        for item in [self._body_item, self._head_item]:
            if item is not None:
                try:
                    self.removeFromGroup(item)
                    item.setParentItem(None)
                except Exception:
                    pass

        if len(self.arrow_points) < 2:
            return

        # Draw the arrow
        self._draw_arrow_components()
        
        # Update the selection rectangle
        if hasattr(self, '_selection_rect') and self._selection_rect:
            self._update_selection_rect()

    def _draw_arrow_components(self):
        """Draw the arrow components (body and head)."""
        pts = self.arrow_points

        # Arrow body
        if self.arrow_style == "zigzag":
            body_path = self._create_zigzag_path(pts)
        elif len(pts) > 2 and self._is_curved():
            body_path = QPainterPath()
            body_path.moveTo(pts[0])
            for i in range(1, len(pts)-1):
                mid = QPointF((pts[i].x() + pts[i+1].x())/2, (pts[i].y() + pts[i+1].y())/2)
                body_path.quadTo(pts[i], mid)
            body_path.lineTo(pts[-1])
        else:
            body_path = QPainterPath()
            body_path.moveTo(pts[0])
            for p in pts[1:]:
                body_path.lineTo(p)

        # Arrow head
        start, end = pts[-2], pts[-1]
        dx, dy = end.x() - start.x(), end.y() - start.y()
        length = math.hypot(dx, dy)
        head_length = ANNOTATION_ARROW_HEAD_LENGTH * max(0.8, self.arrow_width * 0.25)
        if length > 0:
            ratio = max(0, (length - head_length * 0.7) / length)
            new_end = QPointF(start.x() + dx * ratio, start.y() + dy * ratio)
            if self.arrow_style != "zigzag":
                body_path = self._truncate_path_end(body_path, new_end)

        # Create body item
        self._body_item = QGraphicsPathItem(body_path)
        pen = QPen(QColor(self.arrow_color), self.arrow_width * 0.1)
        if self.arrow_style == "dotted":
            pen.setStyle(Qt.PenStyle.DashLine)
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self._body_item.setPen(pen)
        self._body_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.addToGroup(self._body_item)

        # Create head item
        head_path = self._draw_arrow_head_triangle(start, end, head_length)
        self._head_item = QGraphicsPathItem(head_path)
        self._head_item.setPen(QPen(Qt.PenStyle.NoPen))
        self._head_item.setBrush(QBrush(QColor(self.arrow_color)))
        self.addToGroup(self._head_item)

    def _draw_arrow_components_only(self):
        """Redraw only the arrow components without touching the selection rect."""
        # Remove only the arrow sub-items (not the rectangle)
        for item in [self._body_item, self._head_item]:
            if item is not None:
                try:
                    self.removeFromGroup(item)
                    item.setParentItem(None)
                except Exception:
                    pass

        if len(self.arrow_points) < 2:
            return

        # Redraw only the arrow (reuse the existing code)
        self._draw_arrow_components()

    def _update_selection_rect(self):
        """Update the selection rectangle position and size."""
        if not self._selection_rect:
            return
            
        # Recompute bounding box based on current points
        min_x = min(p.x() for p in self.arrow_points)
        max_x = max(p.x() for p in self.arrow_points)
        min_y = min(p.y() for p in self.arrow_points)
        max_y = max(p.y() for p in self.arrow_points)
        
        rect_x = min_x  
        rect_y = min_y 
        rect_width = (max_x - min_x) 
        rect_height = (max_y - min_y)  
        
        self._selection_rect.setPen(QPen(QColor(self.arrow_color), 0.1))
        self._selection_rect.setRect(rect_x, rect_y, rect_width, rect_height)
        
    # Utility methods
    def _is_curved(self):
        return len(self.arrow_points) > 2

    def _truncate_path_end(self, path, new_end):
        if path.isEmpty():
            return path
        polys = path.toSubpathPolygons()
        if not polys or len(polys[0]) < 2:
            return path
        poly = polys[0]
        poly[-1] = new_end
        new_path = QPainterPath()
        new_path.moveTo(poly[0])
        for pt in poly[1:]:
            new_path.lineTo(pt)
        return new_path

    def _draw_arrow_head_triangle(self, start, end, length):
        dx, dy = end.x() - start.x(), end.y() - start.y()
        angle = math.atan2(dy, dx)
        angle_rad = math.radians(ANNOTATION_ARROW_HEAD_ANGLE)
        angle1 = angle + angle_rad
        angle2 = angle - angle_rad
        p1 = QPointF(end.x() - length * math.cos(angle1), end.y() - length * math.sin(angle1))
        p2 = QPointF(end.x() - length * math.cos(angle2), end.y() - length * math.sin(angle2))
        path = QPainterPath()
        path.moveTo(end)
        path.lineTo(p1)
        path.lineTo(p2)
        path.closeSubpath()
        return path

    def _create_zigzag_path(self, pts):
        """Crée un chemin zigzag sinusoïdal segment par segment avec période uniforme,
        et une fin droite sur ~15% du dernier segment pour la tête.
        """
        if len(pts) < 2:
            return QPainterPath()

        # Période fixe en pixels et amplitude en fonction de l'épaisseur
        period_pixels = 2.0
        base_w = getattr(self, "arrow_width", 2.0) or 2.0
        amplitude = 0.6  # amplitude latérale (pixels)

        # Raccourcissement pour la tête (utilisé uniquement pour le dernier segment)
        last_start = pts[-2]
        last_end = pts[-1]
        ldx = last_end.x() - last_start.x()
        ldy = last_end.y() - last_start.y()
        llen = math.hypot(ldx, ldy)
        head_length = ANNOTATION_ARROW_HEAD_LENGTH * max(0.8, base_w * 0.25)
        if llen > 0:
            ratio = max(0.0, (llen - head_length * 0.7) / llen)
            shortened_end = QPointF(last_start.x() + ldx * ratio, last_start.y() + ldy * ratio)
        else:
            shortened_end = last_end

        path = QPainterPath()
        path.moveTo(pts[0])

        for seg_idx in range(len(pts) - 1):
            start_pt = pts[seg_idx]
            end_pt = shortened_end if seg_idx == len(pts) - 2 else pts[seg_idx + 1]

            dx = end_pt.x() - start_pt.x()
            dy = end_pt.y() - start_pt.y()
            seg_len = math.hypot(dx, dy)
            if seg_len <= 1e-6:
                continue

            ux, uy = dx / seg_len, dy / seg_len
            px, py = -uy, ux

            # Nombre d'échantillons (au moins 30)
            num_samples = max(int(seg_len / period_pixels * 10), 30)
            control_points = []
            is_last_segment = (seg_idx == len(pts) - 2)

            for i in range(1, num_samples + 1):
                t = i / num_samples
                bx = start_pt.x() + t * dx
                by = start_pt.y() + t * dy

                if is_last_segment and t > 0.85:
                    fx, fy = bx, by
                else:
                    distance_pixels = t * seg_len
                    osc = amplitude * math.sin(distance_pixels / period_pixels * 2.0 * math.pi)
                    fx = bx + osc * px
                    fy = by + osc * py
                control_points.append(QPointF(fx, fy))

            if control_points:
                # Lissage par courbes quadratiques
                smooth_until = int(len(control_points) * (0.85 if is_last_segment else 1.0))
                if smooth_until > 1:
                    path.quadTo(
                        control_points[0],
                        QPointF(
                            (control_points[0].x() + control_points[1].x()) / 2.0,
                            (control_points[0].y() + control_points[1].y()) / 2.0,
                        ),
                    )
                    for i in range(1, min(smooth_until, len(control_points) - 1)):
                        mid = QPointF(
                            (control_points[i].x() + control_points[i + 1].x()) / 2.0,
                            (control_points[i].y() + control_points[i + 1].y()) / 2.0,
                        )
                        path.quadTo(control_points[i], mid)
                for i in range(smooth_until, len(control_points)):
                    path.lineTo(control_points[i])

        return path

    # Interface methods
    def set_color(self, color):
        self.arrow_color = color
        self.refresh_visual()

    def set_width(self, width):
        self.arrow_width = width
        self.refresh_visual()

    def set_style(self, style):
        self.arrow_style = style
        self.refresh_visual()

    def set_from_player(self, player_id):
        self.from_player = player_id

    def set_to_player(self, player_id):
        self.to_player = player_id

    def refresh_visual(self):
        """Update display after property changes."""
        # Preserve selection state
        was_selected = self.isSelected()
        
        # Redraw only visual components, not the rectangle
        self._draw_arrow_components_only()
        
        # Update only the selection rectangle color
        if self._selection_rect:
            self._selection_rect.setPen(QPen(QColor(self.arrow_color), 0.1))
        
        # Restore selection state
        self.setSelected(was_selected)
        
        # Force visual update
        self.update()


# ===== ZONE MANAGERS =====

class RectangleZoneManager:
    """Manage creation, selection, and storage of rectangular tactical zones."""
    
    def __init__(self, scene):
        self.scene = scene
        self.zones = []
        self.zone_points = []
        self.zone_color = DEFAULT_ZONE_COLOR
        self.zone_width = DEFAULT_ZONE_WIDTH
        self.zone_style = "solid"
        self.zone_fill_alpha = DEFAULT_ZONE_ALPHA
        self.zone_preview = None
        self.selected_zone = None
        self.current_mode = "select"
        
    def set_mode(self, mode):
        """Set the current mode (select/create)."""
        self.current_mode = mode
        self.zone_points = []
        self.remove_zone_preview()
        self.clear_selection()
        
    def clear_selection(self):
        """Clear all zone selections."""
        for zone in list(self.zones):
            try:
                zone.setSelected(False)
            except RuntimeError:
                self.zones.remove(zone)
        self.selected_zone = None
        
    def select_zone(self, zone):
        """Select a specific zone and unselect others."""
        self.clear_selection()
        self.selected_zone = zone
        if zone:
            zone.setSelected(True)
            
    def set_color(self, color):
        """Set color for selected zone or default."""
        if self.selected_zone:
            self.selected_zone.set_color(color)
        else:
            self.zone_color = color
            
    def set_width(self, width):
        """Set width for selected zone or default."""
        if self.selected_zone:
            self.selected_zone.set_width(width)
        else:
            self.zone_width = width
            
    def set_style(self, style):
        """Set border style for selected zone or default ('solid'|'dashed')."""
        normalized = "dashed" if str(style).lower() in ("dash", "dashed", "--") else "solid"
        if self.selected_zone:
            self.selected_zone.set_style(normalized)
        else:
            self.zone_style = normalized

    def set_fill_alpha(self, alpha):
        """Set fill transparency for selected zone or default."""
        if self.selected_zone:
            self.selected_zone.set_fill_alpha(alpha)
        else:
            self.zone_fill_alpha = alpha
            
    def remove_zone_preview(self):
        """Remove the current zone preview."""
        if self.zone_preview:
            try:
                self.scene.removeItem(self.zone_preview)
            except RuntimeError:
                pass
            self.zone_preview = None
            
    def add_point(self, pos):
        """Add a point for zone creation."""
        if len(self.zone_points) < 2:
            self.zone_points.append(pos)
                
    def update_preview(self, pos):
        """Update the zone preview during creation."""
        if not self.zone_points:
            return
            
        self.remove_zone_preview()
        
        if len(self.zone_points) >= 1:
            start = self.zone_points[0]
            rect = QRectF(start, pos).normalized()
            self.zone_preview = RectangleZoneItem(rect, self.zone_color, 
                                               self.zone_width, self.zone_style, 
                                               self.zone_fill_alpha, preview=True)
            self.scene.addItem(self.zone_preview)
                
    def finish_zone(self):
        """Finish creating the current zone."""
        if len(self.zone_points) < 2:
            return False
            
        self.remove_zone_preview()
        
        rect = QRectF(self.zone_points[0], self.zone_points[1]).normalized()
        zone = RectangleZoneItem(rect, self.zone_color, 
                              self.zone_width, self.zone_style, 
                              self.zone_fill_alpha)
            
        self.scene.addItem(zone)
        self.zones.append(zone)
        self.zone_points = []
        return True
        
    def cancel_zone(self):
        """Cancel the current zone creation."""
        self.remove_zone_preview()
        self.zone_points = []
        
    def delete_selected_zone(self):
        """Delete the currently selected zone."""
        if self.selected_zone:
            zone = self.selected_zone
            # Clean up handles first
            zone.cleanup_handles()
            if zone in self.zones:
                self.zones.remove(zone)
            try:
                self.scene.removeItem(zone)
            except RuntimeError:
                pass
        self.clear_selection()


class EllipseZoneManager:
    """Manage creation, selection, and storage of elliptical tactical zones."""
    
    def __init__(self, scene):
        self.scene = scene
        self.zones = []
        self.zone_points = []
        self.zone_color = DEFAULT_ZONE_COLOR
        self.zone_width = DEFAULT_ZONE_WIDTH
        self.zone_style = "solid"
        self.zone_fill_alpha = DEFAULT_ZONE_ALPHA
        self.zone_preview = None
        self.selected_zone = None
        self.current_mode = "select"
        
    def set_mode(self, mode):
        """Set the current mode."""
        self.current_mode = mode
        self.zone_points = []
        self.remove_zone_preview()
        self.clear_selection()
        
    def clear_selection(self):
        """Clear all zone selections."""
        for zone in list(self.zones):
            try:
                zone.setSelected(False)
            except RuntimeError:
                self.zones.remove(zone)
        self.selected_zone = None
        
    def select_zone(self, zone):
        """Select a specific zone and unselect others."""
        self.clear_selection()
        self.selected_zone = zone
        if zone:
            zone.setSelected(True)
            
    def set_color(self, color):
        """Set color for selected zone or default."""
        if self.selected_zone:
            self.selected_zone.set_color(color)
        else:
            self.zone_color = color
            
    def set_width(self, width):
        """Set width for selected zone or default."""
        if self.selected_zone:
            self.selected_zone.set_width(width)
        else:
            self.zone_width = width
            
    def set_style(self, style):
        """Set border style for selected zone or default ('solid'|'dashed')."""
        normalized = "dashed" if str(style).lower() in ("dash", "dashed", "--") else "solid"
        if self.selected_zone:
            self.selected_zone.set_style(normalized)
        else:
            self.zone_style = normalized

    def set_fill_alpha(self, alpha):
        """Set fill transparency for selected zone or default."""
        if self.selected_zone:
            self.selected_zone.set_fill_alpha(alpha)
        else:
            self.zone_fill_alpha = alpha
            
    def remove_zone_preview(self):
        """Remove the current zone preview."""
        if self.zone_preview:
            try:
                self.scene.removeItem(self.zone_preview)
            except RuntimeError:
                pass
            self.zone_preview = None
            
    def add_point(self, pos):
        """Add a point for zone creation."""
        if len(self.zone_points) < 2:
            self.zone_points.append(pos)
                
    def update_preview(self, pos):
        """Update the zone preview during creation."""
        if not self.zone_points:
            return
            
        self.remove_zone_preview()
        
        if len(self.zone_points) >= 1:
            center = self.zone_points[0]
            radius_x = abs(pos.x() - center.x())
            radius_y = abs(pos.y() - center.y())
            rect = QRectF(center.x() - radius_x, center.y() - radius_y, 
                         radius_x * 2, radius_y * 2)
            self.zone_preview = EllipseZoneItem(rect, self.zone_color,
                                              self.zone_width, self.zone_style,
                                              self.zone_fill_alpha, preview=True)
            self.scene.addItem(self.zone_preview)
                
    def finish_zone(self):
        """Finish creating the current zone."""
        if len(self.zone_points) < 2:
            return False
            
        self.remove_zone_preview()
        
        center = self.zone_points[0]
        end = self.zone_points[1]
        radius_x = abs(end.x() - center.x())
        radius_y = abs(end.y() - center.y())
        rect = QRectF(center.x() - radius_x, center.y() - radius_y,
                     radius_x * 2, radius_y * 2)
        zone = EllipseZoneItem(rect, self.zone_color,
                             self.zone_width, self.zone_style,
                             self.zone_fill_alpha)
            
        self.scene.addItem(zone)
        self.zones.append(zone)
        self.zone_points = []
        return True
        
    def cancel_zone(self):
        """Cancel the current zone creation."""
        self.remove_zone_preview()
        self.zone_points = []
        
    def delete_selected_zone(self):
        """Delete the currently selected zone."""
        if self.selected_zone:
            zone = self.selected_zone
            # Clean up handles first
            zone.cleanup_handles()
            if zone in self.zones:
                self.zones.remove(zone)
            try:
                self.scene.removeItem(zone)
            except RuntimeError:
                pass
        self.clear_selection()


# ===== ZONE ITEMS =====

class RectangleZoneItem(QGraphicsItemGroup):
    """Graphical item representing a rectangular tactical zone."""
    
    def __init__(self, rect, color, width, style, fill_alpha, preview=False, parent=None):
        super().__init__(parent)
        
        self.rect = rect
        self.zone_color = color
        self.zone_width = width
        self.zone_style = style
        self.zone_fill_alpha = fill_alpha
        self.rotation_angle = 0
        self.is_preview = preview
        self._updating_handles = False  # Prevent recursion during handle updates
        
        # Resize handles
        self._resize_handles = {}
        self._is_resizing = False
        self._resize_start_pos = None
        self._resize_corner = None
        self._original_rect = None

        
        # Create the main zone item
        self._create_zone_item()
        
        # Create selection rectangle and handles (hidden by default)
        self._create_selection_rect()
        
        # Set flags for interaction
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        

        
    def paint(self, painter, option, widget):
        """Override to remove default white selection rectangle."""
        option_modified = QStyleOptionGraphicsItem(option)
        option_modified.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option_modified, widget)
        
    def _create_zone_item(self):
        """Create the main zone shape."""
        # Create zone item (not as child - use absolute coordinates like before)
        self.zone_item = QGraphicsRectItem(self.rect)
            
        # Set pen with ultra-thin thickness
        pen = QPen(QColor(self.zone_color), 0.1)  # Cosmetic pen (thinnest possible)
        if self.zone_style in ("dashed", "dotted"):
            pen.setStyle(Qt.PenStyle.DashLine)
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
        self.zone_item.setPen(pen)
        
        # Set brush with transparency
        brush_color = QColor(self.zone_color)
        brush_color.setAlpha(self.zone_fill_alpha)
        self.zone_item.setBrush(QBrush(brush_color))
        
        # Apply rotation
        if self.rotation_angle != 0:
            transform = QTransform()
            transform.rotate(self.rotation_angle)
            self.zone_item.setTransform(transform)
            
        self.addToGroup(self.zone_item)
        
    def _create_selection_rect(self):
        """Create selection rectangle."""
        self._selection_rect = QGraphicsRectItem()
        self._selection_rect.setPen(QPen(QColor(self.zone_color), 0.1))  # Ultra-thin selection
        self._selection_rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._selection_rect.setVisible(False)

        self.addToGroup(self._selection_rect)
        
        # Create resize handles
        self._create_resize_handles()
        
   
    def setSelected(self, selected):
        """Handle selection state."""
        super().setSelected(selected)
        if selected:
            self._update_selection_rect()
            self._selection_rect.setVisible(True)
            # Show resize handles
            for handle in self._resize_handles.values():
                if not handle.scene() and self.scene():
                    self.scene().addItem(handle)
                handle.setVisible(True)
            self._update_handles_position()
        else:
            self._selection_rect.setVisible(False)
            # Hide resize handles
            for handle in self._resize_handles.values():
                handle.setVisible(False)
            
    def _update_selection_rect(self):
        """Update selection rectangle to match zone bounds."""
        # Start from the zone local rect (in group coordinates)
        zone_rect = self.zone_item.rect()
        bounds = QRectF(zone_rect)

        # Apply the SAME transform as the shape (rotate around its center)
        if self.rotation_angle != 0:
            center = zone_rect.center()
            transform = QTransform()
            transform.translate(center.x(), center.y())
            transform.rotate(self.rotation_angle)
            transform.translate(-center.x(), -center.y())
            bounds = transform.mapRect(zone_rect)

        # Exact bounds; keep color in sync
        self._selection_rect.setRect(bounds)
        # Keep selection rectangle pen color in sync
        self._selection_rect.setPen(QPen(QColor(self.zone_color), 0.1))  # Ultra-thin selection
    

        
    def set_color(self, color):
        """Change zone color and sync selection rectangle and handles."""
        self.zone_color = color
        pen = self.zone_item.pen()
        pen.setColor(QColor(color))
        self.zone_item.setPen(pen)
        
        brush_color = QColor(color)
        brush_color.setAlpha(self.zone_fill_alpha)
        self.zone_item.setBrush(QBrush(brush_color))
        
        # Sync selection rectangle color
        if hasattr(self, "_selection_rect") and self._selection_rect is not None:
            self._selection_rect.setPen(QPen(QColor(self.zone_color), 0.1))  # Ultra-thin selection
        
    def set_width(self, width):
        """Change zone border width."""
        self.zone_width = width
        # Scale width slower: divide growth factor by 2
        scaled_width = width * 0.25 
        # Create new pen with color and float width
        new_pen = QPen(QColor(self.zone_color), scaled_width)
        new_pen.setStyle(Qt.PenStyle.DashLine if self.zone_style == "dashed" else Qt.PenStyle.SolidLine)
        self.zone_item.setPen(new_pen)
        
    def set_fill_alpha(self, alpha):
        """Change zone fill transparency."""
        self.zone_fill_alpha = alpha
        brush_color = QColor(self.zone_color)
        brush_color.setAlpha(alpha)
        self.zone_item.setBrush(QBrush(brush_color))
        
    def set_style(self, style):
        """Change zone border style ('solid'|'dashed')."""
        self.zone_style = "dashed" if str(style).lower() in ("dash", "dashed", "--") else "solid"
        pen = self.zone_item.pen()
        pen.setStyle(Qt.PenStyle.DashLine if self.zone_style == "dashed" else Qt.PenStyle.SolidLine)
        self.zone_item.setPen(pen)
        
    def set_rotation(self, angle):
        """Set zone rotation angle around the center of the shape."""
        self.rotation_angle = angle
        
        # Get the center of the shape
        rect = self.zone_item.rect()
        center = rect.center()
        
        # Create transform that rotates around the center
        transform = QTransform()
        transform.translate(center.x(), center.y())  # Move to center
        transform.rotate(angle)                       # Rotate
        transform.translate(-center.x(), -center.y()) # Move back
        self.zone_item.setTransform(transform)
        
        if self.isSelected():
            self._update_selection_rect()
            self._update_handles_position()
            
    def get_rotation(self):
        """Get current rotation angle."""
        return self.rotation_angle
    
    def _create_resize_handles(self):
        """Create resize handles at the corners of the selection rectangle."""
        corner_types = ['top_left', 'top_right', 'bottom_left', 'bottom_right']
        
        for corner_type in corner_types:
            handle = ResizeHandle(corner_type, self, self.zone_color)
            handle.setVisible(False)
            self._resize_handles[corner_type] = handle
    
    def _update_handles_position(self):
        """Update positions of resize handles based on selection rectangle."""
        if not self._selection_rect or not self._resize_handles:
            return
            
        # Get selection rectangle bounds in local coordinates
        rect = self._selection_rect.rect()
        
        # Convert to scene coordinates by adding the group's position
        group_pos = self.pos()
        
        handle_positions = {
            'top_left': QPointF(group_pos.x() + rect.left(), group_pos.y() + rect.top()),
            'top_right': QPointF(group_pos.x() + rect.right(), group_pos.y() + rect.top()),
            'bottom_left': QPointF(group_pos.x() + rect.left(), group_pos.y() + rect.bottom()),
            'bottom_right': QPointF(group_pos.x() + rect.right(), group_pos.y() + rect.bottom())
        }
        
        for corner_type, handle in self._resize_handles.items():
            if corner_type in handle_positions:
                handle.setPos(handle_positions[corner_type])
    
    def start_resize(self, corner_type, scene_pos):
        """Start resize operation."""
        
        
        self._is_resizing = True
        self._resize_corner = corner_type
        self._resize_start_pos = scene_pos
        # Store original rect in ABSOLUTE coordinates (current position after any moves)
        self._original_rect = QRectF(self.rect)
        
        
        # Disable normal movement during resize
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
    
    def update_resize(self, corner_type, scene_pos):
        """Update zone rectangle during resize operation (rotation-aware)."""
        if not self._is_resizing or not self._original_rect:
            return

        # Convert dragged scene position to group-local coordinates
        group_pos = self.pos()
        new_corner_local = QPointF(scene_pos.x() - group_pos.x(), scene_pos.y() - group_pos.y())

        # Original rotated bounds (axis-aligned) of the rectangle
        orig_rect = QRectF(self._original_rect)
        angle = math.radians(self.rotation_angle)
        c = abs(math.cos(angle))
        s = abs(math.sin(angle))
        center_orig = orig_rect.center()

        # Build original axis-aligned bounding box after rotation
        bw_orig = orig_rect.width() * c + orig_rect.height() * s
        bh_orig = orig_rect.width() * s + orig_rect.height() * c
        bounds_orig = QRectF(center_orig.x() - bw_orig / 2.0,
                             center_orig.y() - bh_orig / 2.0,
                             bw_orig, bh_orig)

        # Opposite corner fixed; dragged corner replaced by new position
        corners = {
            'top_left': QPointF(bounds_orig.left(), bounds_orig.top()),
            'top_right': QPointF(bounds_orig.right(), bounds_orig.top()),
            'bottom_left': QPointF(bounds_orig.left(), bounds_orig.bottom()),
            'bottom_right': QPointF(bounds_orig.right(), bounds_orig.bottom()),
        }
        opposite = {
            'top_left': 'bottom_right',
            'bottom_right': 'top_left',
            'top_right': 'bottom_left',
            'bottom_left': 'top_right',
        }
        if corner_type not in corners:
            return

        fixed = corners[opposite[corner_type]]
        new_bounds = QRectF(new_corner_local, fixed).normalized()

        # Compute new width/height of the underlying unrotated rect so that
        # its rotated bounding box equals new_bounds
        bw = new_bounds.width()
        bh = new_bounds.height()
        det = c * c - s * s  # = cos(2a)

        if abs(det) < 1e-6:
            # Fallback: scale with ratios preserving previous aspect
            scale_w = bw / max(bw_orig, 1e-6)
            scale_h = bh / max(bh_orig, 1e-6)
            new_w = max(1.0, orig_rect.width() * scale_w)
            new_h = max(1.0, orig_rect.height() * scale_h)
        else:
            new_w = max(1.0, (bw * c - bh * s) / det)
            new_h = max(1.0, (bh * c - bw * s) / det)

        # New center is the center of the new bounds
        center_new = new_bounds.center()
        self.rect = QRectF(center_new.x() - new_w / 2.0,
                           center_new.y() - new_h / 2.0,
                           new_w, new_h)

        # Apply transform rotation around the new center
        transform = QTransform()
        transform.translate(center_new.x(), center_new.y())
        transform.rotate(self.rotation_angle)
        transform.translate(-center_new.x(), -center_new.y())
        self.zone_item.setRect(self.rect)
        self.zone_item.setTransform(transform)

        # Update selection rectangle and handles to match new bounds
        self._update_selection_rect()
        self._update_handles_position()
    
    def end_resize(self):
        """End resize operation."""
        
        
        self._is_resizing = False
        self._resize_corner = None
        self._resize_start_pos = None
        # Update _original_rect to current position for next resize
        self._original_rect = QRectF(self.rect)
        
        
        # Re-enable normal movement
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
    
    def end_movement(self):
        """Called when movement ends to update _original_rect."""
        if hasattr(self, '_original_rect') and self._original_rect:
            old_original = QRectF(self._original_rect)
            self._original_rect = QRectF(self.rect)
            
    
    def _recreate_zone_item(self):
        """Recreate the zone item with current rectangle."""
        # Remove old zone item from scene
        if self.zone_item and self.scene():
            try:
                self.scene().removeItem(self.zone_item)
            except Exception:
                pass
        # Create new item from absolute rect
        self._create_zone_item()
        if self.scene():
            self.scene().addItem(self.zone_item)
    
    def cleanup_handles(self):
        """Clean up handles when zone is deleted."""
        for handle in self._resize_handles.values():
            if handle.scene():
                handle.scene().removeItem(handle)
        self._resize_handles.clear()
    
    def _create_resize_handles(self):
        """Create resize handles at the corners of the selection rectangle."""
        corner_types = ['top_left', 'top_right', 'bottom_left', 'bottom_right']
        
        for corner_type in corner_types:
            handle = ResizeHandle(corner_type, self, self.zone_color)
            handle.setVisible(False)
            self._resize_handles[corner_type] = handle
    
    def _update_handles_position(self):
        """Update positions of resize handles based on selection rectangle."""
        if not self._selection_rect or not self._resize_handles:
            return
            
        # Get selection rectangle bounds in local coordinates
        rect = self._selection_rect.rect()
        
        # Convert to scene coordinates by adding the group's position
        group_pos = self.pos()
        
        handle_positions = {
            'top_left': QPointF(group_pos.x() + rect.left(), group_pos.y() + rect.top()),
            'top_right': QPointF(group_pos.x() + rect.right(), group_pos.y() + rect.top()),
            'bottom_left': QPointF(group_pos.x() + rect.left(), group_pos.y() + rect.bottom()),
            'bottom_right': QPointF(group_pos.x() + rect.right(), group_pos.y() + rect.bottom())
        }
        
        for corner_type, handle in self._resize_handles.items():
            if corner_type in handle_positions:
                handle.setPos(handle_positions[corner_type])
    
    def start_resize(self, corner_type, scene_pos):
        """Start resize operation."""
        self._is_resizing = True
        self._resize_corner = corner_type
        self._resize_start_pos = scene_pos
        # Store original rect in ABSOLUTE coordinates (consistent with update)
        self._original_rect = QRectF(self.rect)
        
        
        # Disable normal movement during resize
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
    
    def update_resize(self, corner_type, scene_pos):
        """Update ellipse rectangle during resize operation (rotation-aware)."""
        if not self._is_resizing or not self._original_rect:
            return

        group_pos = self.pos()
        new_corner_local = QPointF(scene_pos.x() - group_pos.x(), scene_pos.y() - group_pos.y())

        orig_rect = QRectF(self._original_rect)
        angle = math.radians(self.rotation_angle)
        c = abs(math.cos(angle))
        s = abs(math.sin(angle))
        center_orig = orig_rect.center()

        bw_orig = orig_rect.width() * c + orig_rect.height() * s
        bh_orig = orig_rect.width() * s + orig_rect.height() * c
        bounds_orig = QRectF(center_orig.x() - bw_orig / 2.0,
                             center_orig.y() - bh_orig / 2.0,
                             bw_orig, bh_orig)

        corners = {
            'top_left': QPointF(bounds_orig.left(), bounds_orig.top()),
            'top_right': QPointF(bounds_orig.right(), bounds_orig.top()),
            'bottom_left': QPointF(bounds_orig.left(), bounds_orig.bottom()),
            'bottom_right': QPointF(bounds_orig.right(), bounds_orig.bottom()),
        }
        opposite = {
            'top_left': 'bottom_right',
            'bottom_right': 'top_left',
            'top_right': 'bottom_left',
            'bottom_left': 'top_right',
        }
        if corner_type not in corners:
            return

        fixed = corners[opposite[corner_type]]
        new_bounds = QRectF(new_corner_local, fixed).normalized()

        bw = new_bounds.width()
        bh = new_bounds.height()
        det = c * c - s * s

        if abs(det) < 1e-6:
            scale_w = bw / max(bw_orig, 1e-6)
            scale_h = bh / max(bh_orig, 1e-6)
            new_w = max(1.0, orig_rect.width() * scale_w)
            new_h = max(1.0, orig_rect.height() * scale_h)
        else:
            new_w = max(1.0, (bw * c - bh * s) / det)
            new_h = max(1.0, (bh * c - bw * s) / det)

        center_new = new_bounds.center()
        self.rect = QRectF(center_new.x() - new_w / 2.0,
                           center_new.y() - new_h / 2.0,
                           new_w, new_h)

        transform = QTransform()
        transform.translate(center_new.x(), center_new.y())
        transform.rotate(self.rotation_angle)
        transform.translate(-center_new.x(), -center_new.y())
        self.zone_item.setRect(self.rect)
        self.zone_item.setTransform(transform)

        self._update_selection_rect()
        self._update_handles_position()
    
    def end_resize(self):
        """End resize operation."""
        
        
        self._is_resizing = False
        self._resize_corner = None
        self._resize_start_pos = None
        # Update _original_rect to current position for next resize
        self._original_rect = QRectF(self.rect)
        
        
        # Re-enable normal movement
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
    
    def end_movement(self):
        """Called when movement ends to update _original_rect."""
        if hasattr(self, '_original_rect') and self._original_rect:
            old_original = QRectF(self._original_rect)
            self._original_rect = QRectF(self.rect)
            
    
    def _recreate_zone_item(self):
        """Recreate the zone item with current rectangle."""
        # Remove old zone item from scene
        if self.zone_item and self.scene():
            try:
                self.scene().removeItem(self.zone_item)
            except Exception:
                pass
        # Create new item from absolute rect
        self._create_zone_item()
        if self.scene():
            self.scene().addItem(self.zone_item)
    
    def cleanup_handles(self):
        """Clean up handles when zone is deleted."""
        for handle in self._resize_handles.values():
            if handle.scene():
                handle.scene().removeItem(handle)
        self._resize_handles.clear()
    
    def itemChange(self, change, value):
        """Handle move operations only - resize is handled by handles."""
        from PyQt6.QtWidgets import QGraphicsItem
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.isSelected():
            # Don't move if we're in resize mode (handles are controlling the resize)
            if self._is_resizing:
                return self.pos()
                
            # Do not change self.rect during movement. Keep rect in local coords;
            # moving the group is enough. Only update visuals.
                
            # Update selection rect and handles DURING move (real-time)
            if hasattr(self, '_selection_rect'):
                self._update_selection_rect()
                self._update_handles_position()
            
        # After the position has actually changed, sync _original_rect to the new rect
        from PyQt6.QtWidgets import QGraphicsItem
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and hasattr(self, 'rect'):
            if hasattr(self, '_original_rect'):
                self._original_rect = QRectF(self.rect)
                
        
        return super().itemChange(change, value)


class EllipseZoneItem(QGraphicsItemGroup):
    """Graphical item representing an elliptical tactical zone."""
    
    def __init__(self, rect, color, width, style, fill_alpha, preview=False, parent=None):
        super().__init__(parent)
        
        self.rect = rect
        self.zone_color = color
        self.zone_width = width
        self.zone_style = style
        self.zone_fill_alpha = fill_alpha
        self.rotation_angle = 0
        self.is_preview = preview
        self._updating_handles = False  # Prevent recursion during handle updates
        
        # Resize handles
        self._resize_handles = {}
        self._is_resizing = False
        self._resize_start_pos = None
        self._resize_corner = None
        self._original_rect = None

        
        # Create the main zone item
        self._create_zone_item()
        
        # Create selection rectangle (hidden by default)
        self._create_selection_rect()
        
        # Set flags for interaction
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        

        
    def paint(self, painter, option, widget):
        """Override to remove default white selection rectangle."""
        option_modified = QStyleOptionGraphicsItem(option)
        option_modified.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option_modified, widget)
        
    def _create_zone_item(self):
        """Create the main zone shape."""
        # Create zone item (not as child - use absolute coordinates like before)
        self.zone_item = QGraphicsEllipseItem(self.rect)
            
        # Set pen with ultra-thin thickness
        pen = QPen(QColor(self.zone_color), 0.1)  # Cosmetic pen (thinnest possible)
        if self.zone_style in ("dashed", "dotted"):
            pen.setStyle(Qt.PenStyle.DashLine)
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
        self.zone_item.setPen(pen)
        
        # Set brush with transparency
        brush_color = QColor(self.zone_color)
        brush_color.setAlpha(self.zone_fill_alpha)
        self.zone_item.setBrush(QBrush(brush_color))
        
        # Apply rotation
        if self.rotation_angle != 0:
            transform = QTransform()
            transform.rotate(self.rotation_angle)
            self.zone_item.setTransform(transform)
            
        self.addToGroup(self.zone_item)
        
    def _create_selection_rect(self):
        """Create selection rectangle."""
        self._selection_rect = QGraphicsRectItem()
        self._selection_rect.setPen(QPen(QColor(self.zone_color), 0.1))  # Ultra-thin selection
        self._selection_rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._selection_rect.setVisible(False)

        self.addToGroup(self._selection_rect)
        
        # Create resize handles
        self._create_resize_handles()
        
    def setSelected(self, selected):
        """Handle selection state."""
        super().setSelected(selected)
        if selected:
            self._update_selection_rect()
            self._selection_rect.setVisible(True)
            # Show resize handles
            for handle in self._resize_handles.values():
                if not handle.scene() and self.scene():
                    self.scene().addItem(handle)
                handle.setVisible(True)
            self._update_handles_position()
        else:
            self._selection_rect.setVisible(False)
            # Hide resize handles
            for handle in self._resize_handles.values():
                handle.setVisible(False)
            
    def _update_selection_rect(self):
        """Update selection rectangle and resize handles to match zone bounds.

        For an ellipse, use the minimal axis-aligned bounding box of the rotated
        ellipse rather than transforming the rect as if it were a box.
        """
        rect = self.zone_item.rect()
        center = rect.center()
        a = rect.width() / 2.0
        b = rect.height() / 2.0
        theta = math.radians(self.rotation_angle)
        c = math.cos(theta)
        s = math.sin(theta)

        half_w = math.sqrt((a * c) ** 2 + (b * s) ** 2)
        half_h = math.sqrt((a * s) ** 2 + (b * c) ** 2)
        bounds = QRectF(center.x() - half_w,
                        center.y() - half_h,
                        2.0 * half_w,
                        2.0 * half_h)

        self._selection_rect.setRect(bounds)
        self._selection_rect.setPen(QPen(QColor(self.zone_color), 0.1))  # Ultra-thin selection
        

    
    def itemChange(self, change, value):
        """Handle move operations only - resize is handled by handles."""
        from PyQt6.QtWidgets import QGraphicsItem
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.isSelected():
            # Don't move if we're in resize mode (handles are controlling the resize)
            if self._is_resizing:
                return self.pos()
                
            # Do not change self.rect during movement. Keep rect in local coords;
            # moving the group is enough. Only update visuals.
                
            # Update selection rect and handles DURING move (real-time)
            if hasattr(self, '_selection_rect'):
                self._update_selection_rect()
                self._update_handles_position()
            
        # After the position has actually changed, sync _original_rect to the new rect
        from PyQt6.QtWidgets import QGraphicsItem
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and hasattr(self, 'rect'):
            if hasattr(self, '_original_rect'):
                self._original_rect = QRectF(self.rect)
        
        return super().itemChange(change, value)
    
    def _handle_resize(self, handle_index, new_pos):
        """Resize the ellipse based on handle movement."""
        current_rect = self.zone_item.rect()
        
        # Handle index mapping (same as rectangle):
        # 0: top-left, 1: top-right, 2: bottom-left, 3: bottom-right
        # 4: top edge, 5: right edge, 6: bottom edge, 7: left edge
        
        if handle_index == 0:  # top-left
            current_rect.setTopLeft(new_pos)
        elif handle_index == 1:  # top-right
            current_rect.setTopRight(new_pos)
        elif handle_index == 2:  # bottom-left
            current_rect.setBottomLeft(new_pos)
        elif handle_index == 3:  # bottom-right
            current_rect.setBottomRight(new_pos)
        elif handle_index == 4:  # top edge
            current_rect.setTop(new_pos.y())
        elif handle_index == 5:  # right edge
            current_rect.setRight(new_pos.x())
        elif handle_index == 6:  # bottom edge
            current_rect.setBottom(new_pos.y())
        elif handle_index == 7:  # left edge
            current_rect.setLeft(new_pos.x())
        
        # Update the zone rectangle (ellipse uses same bounding rect)
        self.rect = current_rect
        self.zone_item.setRect(current_rect)
        self._update_selection_rect()
        
    def set_color(self, color):
        """Change zone color."""
        self.zone_color = color
        pen = self.zone_item.pen()
        pen.setColor(QColor(color))
        self.zone_item.setPen(pen)
        
        brush_color = QColor(color)
        brush_color.setAlpha(self.zone_fill_alpha)
        self.zone_item.setBrush(QBrush(brush_color))
        
        # Sync selection rectangle color
        if hasattr(self, "_selection_rect") and self._selection_rect is not None:
            self._selection_rect.setPen(QPen(QColor(self.zone_color), 0.1))  # Ultra-thin selection
        
    def set_width(self, width):
        """Change zone border width."""
        self.zone_width = width
        # Scale width slower: divide growth factor by 2
        scaled_width = width * 0.25
        # Create new pen with color and float width
        new_pen = QPen(QColor(self.zone_color), scaled_width)
        new_pen.setStyle(Qt.PenStyle.DashLine if self.zone_style == "dashed" else Qt.PenStyle.SolidLine)
        self.zone_item.setPen(new_pen)
        
    def set_fill_alpha(self, alpha):
        """Change zone fill transparency."""
        self.zone_fill_alpha = alpha
        brush_color = QColor(self.zone_color)
        brush_color.setAlpha(alpha)
        self.zone_item.setBrush(QBrush(brush_color))
        
    def set_style(self, style):
        """Change zone border style ('solid'|'dashed')."""
        self.zone_style = "dashed" if str(style).lower() in ("dash", "dashed", "--") else "solid"
        pen = self.zone_item.pen()
        pen.setStyle(Qt.PenStyle.DashLine if self.zone_style == "dashed" else Qt.PenStyle.SolidLine)
        self.zone_item.setPen(pen)
        
    def set_rotation(self, angle):
        """Set zone rotation angle around the center of the shape."""
        self.rotation_angle = angle
        
        # Get the center of the shape
        rect = self.zone_item.rect()
        center = rect.center()
        
        # Create transform that rotates around the center
        transform = QTransform()
        transform.translate(center.x(), center.y())  # Move to center
        transform.rotate(angle)                       # Rotate
        transform.translate(-center.x(), -center.y()) # Move back
        self.zone_item.setTransform(transform)
        
        if self.isSelected():
            self._update_selection_rect()
            self._update_handles_position()
            
    def get_rotation(self):
        """Get current rotation angle."""
        return self.rotation_angle
    
    def _create_resize_handles(self):
        """Create resize handles at the corners of the selection rectangle."""
        corner_types = ['top_left', 'top_right', 'bottom_left', 'bottom_right']
        
        for corner_type in corner_types:
            handle = ResizeHandle(corner_type, self, self.zone_color)
            handle.setVisible(False)
            self._resize_handles[corner_type] = handle
    
    def _update_handles_position(self):
        """Update positions of resize handles based on selection rectangle."""
        if not self._selection_rect or not self._resize_handles:
            return
            
        # Get selection rectangle bounds in local coordinates
        rect = self._selection_rect.rect()
        
        # Convert to scene coordinates by adding the group's position
        group_pos = self.pos()
        
        handle_positions = {
            'top_left': QPointF(group_pos.x() + rect.left(), group_pos.y() + rect.top()),
            'top_right': QPointF(group_pos.x() + rect.right(), group_pos.y() + rect.top()),
            'bottom_left': QPointF(group_pos.x() + rect.left(), group_pos.y() + rect.bottom()),
            'bottom_right': QPointF(group_pos.x() + rect.right(), group_pos.y() + rect.bottom())
        }
        
        for corner_type, handle in self._resize_handles.items():
            if corner_type in handle_positions:
                handle.setPos(handle_positions[corner_type])
    
    def start_resize(self, corner_type, scene_pos):
        """Start resize operation."""
        self._is_resizing = True
        self._resize_corner = corner_type
        self._resize_start_pos = scene_pos
        # Store original rect in ABSOLUTE coordinates (consistent with update)
        self._original_rect = QRectF(self.rect)
        
        
        # Disable normal movement during resize
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
    
    def update_resize(self, corner_type, scene_pos):
        """Update ellipse rectangle during resize operation (rotation-aware)."""
        if not self._is_resizing or not self._original_rect:
            return

        # Work in group-local coordinates
        group_pos = self.pos()
        new_corner_local = QPointF(scene_pos.x() - group_pos.x(), scene_pos.y() - group_pos.y())

        # Original ellipse rect (unrotated) and its rotated AABB
        orig_rect = QRectF(self._original_rect)
        angle = math.radians(self.rotation_angle)
        c = math.cos(angle)
        s = math.sin(angle)
        c2 = c * c
        s2 = s * s
        center_orig = orig_rect.center()
        a0 = max(1e-6, orig_rect.width() / 2.0)
        b0 = max(1e-6, orig_rect.height() / 2.0)
        half_w0 = math.sqrt((a0 * c) ** 2 + (b0 * s) ** 2)
        half_h0 = math.sqrt((a0 * s) ** 2 + (b0 * c) ** 2)
        bounds_orig = QRectF(center_orig.x() - half_w0,
                             center_orig.y() - half_h0,
                             2.0 * half_w0,
                             2.0 * half_h0)

        corners = {
            'top_left': QPointF(bounds_orig.left(), bounds_orig.top()),
            'top_right': QPointF(bounds_orig.right(), bounds_orig.top()),
            'bottom_left': QPointF(bounds_orig.left(), bounds_orig.bottom()),
            'bottom_right': QPointF(bounds_orig.right(), bounds_orig.bottom()),
        }
        opposite = {
            'top_left': 'bottom_right',
            'bottom_right': 'top_left',
            'top_right': 'bottom_left',
            'bottom_left': 'top_right',
        }
        if corner_type not in corners:
            return

        fixed = corners[opposite[corner_type]]
        new_bounds = QRectF(new_corner_local, fixed).normalized()

        # New AABB half sizes
        A = max(1.0, new_bounds.width() / 2.0)
        B = max(1.0, new_bounds.height() / 2.0)
        D = c2 - s2  # cos(2θ)

        if abs(D) < 1e-6:
            # fallback scaling at singular angles
            scale_w = (A * 2.0) / max(bounds_orig.width(), 1e-6)
            scale_h = (B * 2.0) / max(bounds_orig.height(), 1e-6)
            a = max(1.0, a0 * scale_w)
            b = max(1.0, b0 * scale_h)
        else:
            a2 = max(1e-6, (A * A * c2 - B * B * s2) / D)
            b2 = max(1e-6, (B * B * c2 - A * A * s2) / D)
            a = math.sqrt(a2)
            b = math.sqrt(b2)

        # Rebuild the unrotated rect from center and (a,b)
        center_new = new_bounds.center()
        self.rect = QRectF(center_new.x() - a, center_new.y() - b, 2.0 * a, 2.0 * b)

        # Apply rotation around the center
        transform = QTransform()
        transform.translate(center_new.x(), center_new.y())
        transform.rotate(self.rotation_angle)
        transform.translate(-center_new.x(), -center_new.y())
        self.zone_item.setRect(self.rect)
        self.zone_item.setTransform(transform)

        # Sync selection rectangle and handles
        self._update_selection_rect()
        self._update_handles_position()
    
    def end_resize(self):
        """End resize operation."""
        
        
        self._is_resizing = False
        self._resize_corner = None
        self._resize_start_pos = None
        # Update _original_rect to current position for next resize
        self._original_rect = QRectF(self.rect)
        
        
        # Re-enable normal movement
        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
    
    def end_movement(self):
        """Called when movement ends to update _original_rect."""
        if hasattr(self, '_original_rect') and self._original_rect:
            old_original = QRectF(self._original_rect)
            self._original_rect = QRectF(self.rect)
            
    
    def _recreate_zone_item(self):
        """Recreate the zone item with current rectangle."""
        # Remove old zone item from scene
        if self.zone_item and self.scene():
            try:
                self.scene().removeItem(self.zone_item)
            except Exception:
                pass
        # Create new item from absolute rect
        self._create_zone_item()
        if self.scene():
            self.scene().addItem(self.zone_item)
    
    def cleanup_handles(self):
        """Clean up handles when zone is deleted."""
        for handle in self._resize_handles.values():
            if handle.scene():
                handle.scene().removeItem(handle)
        self._resize_handles.clear()


# ===== Cone ZONE ITEM =====
class ConeZoneItem(QGraphicsItemGroup):
    """Graphical item representing a conical (sector) tactical zone.

    Defined by an apex point, an orientation (degrees), a radius, and a spread angle.
    """
    def __init__(self, apex, direction_point, color, width, style, fill_alpha,
                 spread_deg=30.0, preview=False, parent=None, edge_point_2=None):
        super().__init__(parent)
        self.apex = QPointF(apex)
        self.direction_point = QPointF(direction_point)
        self.edge_point_2 = QPointF(edge_point_2) if edge_point_2 is not None else None

        self.zone_color = color
        self.zone_width = width
        self.zone_style = style
        self.zone_fill_alpha = fill_alpha
        self.spread_deg = float(spread_deg)
        self.is_preview = preview

        # --- Canonical parameters for rotation ---
        dx = self.direction_point.x() - self.apex.x()
        dy = self.direction_point.y() - self.apex.y()
        self.radius = max(1.0, math.hypot(dx, dy))
        # orientation in Qt convention (0°=+X, CCW positif)
        self.orientation_deg = -math.degrees(math.atan2(dy, dx))
        # Mémorise si l’utilisateur a défini 2 bords (mode "two-edges")
        self._two_edges = self.edge_point_2 is not None
        # ----------------------------------------

        self._resize_handles = {}
        self._is_resizing = False
        self._resize_start_pos = None
        self._resize_corner = None
        self._original_points = None

        self._create_zone_item()
        self._create_selection_rect()

        from PyQt6.QtWidgets import QGraphicsItem
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    
    def _build_path(self):
        """Build a sector centered at apex with correct angle convention for Qt."""
        def qt_deg(d):           # math → Qt screen coords
            return -float(d)     # invert because Y is down in Qt

        path = QPainterPath(self.apex)

        if self.edge_point_2 is not None:
            # Build from the two edge points
            dx1 = self.direction_point.x() - self.apex.x()
            dy1 = self.direction_point.y() - self.apex.y()
            dx2 = self.edge_point_2.x()  - self.apex.x()
            dy2 = self.edge_point_2.y()  - self.apex.y()
            r1 = max(1.0, math.hypot(dx1, dy1))
            r2 = max(1.0, math.hypot(dx2, dy2))
            R  = max(r1, r2)

            a1 = math.degrees(math.atan2(-dy1, dx1))  # math angle (y up)
            a2 = math.degrees(math.atan2(-dy2, dx2))

            # shortest sweep from a1 → a2
            delta = (a2 - a1 + 540.0) % 360.0 - 180.0  # (-180,180]
            if delta >= 0:
                start_angle = a1
                sweep       = delta
            else:
                start_angle = a2
                sweep       = -delta

            rect = QRectF(self.apex.x() - R, self.apex.y() - R, 2 * R, 2 * R)

            # move to first edge, then arc with Qt angles
            start_rad = math.radians(qt_deg(start_angle))
            sx = self.apex.x() + R * math.cos(start_rad)
            sy = self.apex.y() - R * math.sin(start_rad)
            path.moveTo(self.apex)
            path.lineTo(QPointF(sx, sy))
            path.arcTo(rect, qt_deg(start_angle), -sweep)  # NEGATIVE sweep for consistency
            path.closeSubpath()
            return path

        # Symmetric cone: keep interior angle self.spread_deg and rotate with self.orientation_deg
        start_angle = self.orientation_deg - self.spread_deg / 2.0  # math angle
        qt_start = qt_deg(start_angle)
        qt_sweep = -self.spread_deg   # NEGATIVE sweep

        rect = QRectF(self.apex.x() - self.radius, self.apex.y() - self.radius,
                      2 * self.radius, 2 * self.radius)

        path.moveTo(self.apex)
        start_rad = math.radians(qt_start)
        sx = self.apex.x() + self.radius * math.cos(start_rad)
        sy = self.apex.y() - self.radius * math.sin(start_rad)
        path.lineTo(QPointF(sx, sy))
        path.arcTo(rect, qt_start, qt_sweep)
        path.closeSubpath()
        return path
    
    def _create_zone_item(self):
        self.zone_item = QGraphicsPathItem()
        self.zone_item.setPath(self._build_path())
        # Match other zones: use scaled width from zone_width
        scaled_width = self.zone_width * 0.25
        pen = QPen(QColor(self.zone_color), scaled_width)
        pen.setStyle(Qt.PenStyle.DashLine if self.zone_style in ("dashed", "dotted") else Qt.PenStyle.SolidLine)
        self.zone_item.setPen(pen)
        brush_color = QColor(self.zone_color)
        brush_color.setAlpha(self.zone_fill_alpha)
        self.zone_item.setBrush(QBrush(brush_color))
        self.addToGroup(self.zone_item)
    
    def _create_selection_rect(self):
        self._selection_rect = QGraphicsRectItem()
        self._selection_rect.setPen(QPen(QColor(self.zone_color), 0.1))
        self._selection_rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._selection_rect.setVisible(False)
        self.addToGroup(self._selection_rect)
        self._create_resize_handles()
    
    def _create_resize_handles(self):
            """Create resize handles at the corners of the selection rectangle."""
            corner_types = ['top_left', 'top_right', 'bottom_left', 'bottom_right']
            
            for corner_type in corner_types:
                handle = ResizeHandle(corner_type, self, self.zone_color)
                handle.setVisible(False)
                self._resize_handles[corner_type] = handle


    def paint(self, painter, option, widget):
        """Override to remove default white square"""
        option_modified = QStyleOptionGraphicsItem(option)
        option_modified.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option_modified, widget)

    def _update_selection_rect(self):
        bounds = self.zone_item.path().boundingRect()
        self._selection_rect.setRect(bounds)
        self._selection_rect.setPen(QPen(QColor(self.zone_color), 0.1))
    

    def setSelected(self, selected):
        super().setSelected(selected)
        self._selection_rect.setVisible(bool(selected))
        if selected:
            self._update_selection_rect()
    
    def set_color(self, color):
        self.zone_color = color
        pen = self.zone_item.pen()
        pen.setColor(QColor(color))
        self.zone_item.setPen(pen)
        brush_color = QColor(color)
        brush_color.setAlpha(self.zone_fill_alpha)
        self.zone_item.setBrush(QBrush(brush_color))
        self._update_selection_rect()
    
    def set_width(self, width):
        self.zone_width = width
        scaled_width = width * 0.25
        pen = QPen(QColor(self.zone_color), scaled_width)
        pen.setStyle(Qt.PenStyle.DashLine if self.zone_style == "dashed" else Qt.PenStyle.SolidLine)
        self.zone_item.setPen(pen)
        self._update_selection_rect()
    
    def set_fill_alpha(self, alpha):
        self.zone_fill_alpha = alpha
        brush_color = QColor(self.zone_color)
        brush_color.setAlpha(alpha)
        self.zone_item.setBrush(QBrush(brush_color))
        self._update_selection_rect()
    
    def set_style(self, style):
        self.zone_style = "dashed" if str(style).lower() in ("dash", "dashed", "--") else "solid"
        pen = self.zone_item.pen()
        pen.setStyle(Qt.PenStyle.DashLine if self.zone_style == "dashed" else Qt.PenStyle.SolidLine)
        self.zone_item.setPen(pen)
        self._update_selection_rect()
    
    # --- rotation qui conserve l’angle intérieur et le rayon ---
    def set_rotation(self, angle_deg: float):
        self.orientation_deg = float(angle_deg)
        self.zone_item.setPath(self._build_path())
        self._update_selection_rect()

    def get_rotation(self) -> float:
        return float(self.orientation_deg)

    # --- si tu changes l’angle intérieur, on reconstruit sans toucher au rayon ---
    def set_spread_deg(self, angle_deg: float):
        self.spread_deg = float(max(0.0, angle_deg))
        self.zone_item.setPath(self._build_path())
        self._update_selection_rect()

    def get_spread_deg(self) -> float:
        return float(self.spread_deg)

class ConeZoneManager:
    """Manage creation, selection, and storage of conical tactical zones (2-click flow)."""
    def __init__(self, scene):
        self.scene = scene
        self.zones = []
        self.zone_points = []                # [apex, end] pendant la création
        self.zone_color = DEFAULT_ZONE_COLOR
        self.zone_width = DEFAULT_ZONE_WIDTH
        self.zone_style = "solid"
        self.zone_fill_alpha = DEFAULT_ZONE_ALPHA
        self.zone_spread_deg = 60.0          # angle intérieur par défaut (modif ensuite dans props)
        self.zone_preview = None
        self.selected_zone = None
        self.current_mode = "select"

    # ====== état / sélection ======
    def set_mode(self, mode):
        self.current_mode = mode
        self.zone_points = []
        self.remove_zone_preview()
        self.clear_selection()

    def clear_selection(self):
        for zone in list(self.zones):
            try:
                zone.setSelected(False)
            except RuntimeError:
                self.zones.remove(zone)
        self.selected_zone = None

    def select_zone(self, zone):
        self.clear_selection()
        self.selected_zone = zone
        if zone:
            zone.setSelected(True)

    def setSelected(self, selected):
        if self.selected_zone:
            self.selected_zone.setSelected(selected)

    # ====== styles par défaut / sélection ======
    def set_color(self, color):
        if self.selected_zone:
            self.selected_zone.set_color(color)
        else:
            self.zone_color = color

    def set_width(self, width):
        if self.selected_zone:
            self.selected_zone.set_width(width)
        else:
            self.zone_width = width

    def set_style(self, style):
        normalized = "dashed" if str(style).lower() in ("dash", "dashed", "--") else "solid"
        if self.selected_zone:
            self.selected_zone.set_style(normalized)
        else:
            self.zone_style = normalized

    def set_fill_alpha(self, alpha):
        if self.selected_zone:
            self.selected_zone.set_fill_alpha(alpha)
        else:
            self.zone_fill_alpha = alpha

    # ====== cycle création (2 clics) ======
    def remove_zone_preview(self):
        if self.zone_preview:
            try:
                self.scene.removeItem(self.zone_preview)
            except RuntimeError:
                pass
            self.zone_preview = None

    def add_point(self, pos):
        """Click handler (comme rect/ellipse)."""
        if len(self.zone_points) < 2:
            self.zone_points.append(QPointF(pos))

    def update_preview(self, pos):
        """Preview live (après clic 1, sans drag)."""
        if not self.zone_points:
            return

        self.remove_zone_preview()

        # 1 point → apex fixé, le rayon suit la souris ; on affiche un cône
        apex = self.zone_points[0]
        end = QPointF(pos)

        # Construire un item cone en preview, angle intérieur = self.zone_spread_deg
        preview = ConeZoneItem(
            apex=apex,
            direction_point=end,
            color=self.zone_color,
            width=self.zone_width,
            style=self.zone_style,
            fill_alpha=self.zone_fill_alpha,
            spread_deg=self.zone_spread_deg,
            preview=True
        )
        # Le preview ne doit pas intercepter les clics
        from PyQt6.QtWidgets import QGraphicsItem
        preview.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        preview.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        preview.setZValue(1000)

        self.zone_preview = preview
        self.scene.addItem(self.zone_preview)

    def finish_zone(self):
        """Finalise au 2e clic (comme rect/ellipse)."""
        if len(self.zone_points) < 2:
            return False

        self.remove_zone_preview()

        apex, end = self.zone_points[0], self.zone_points[1]
        zone = ConeZoneItem(
            apex=apex,
            direction_point=end,
            color=self.zone_color,
            width=self.zone_width,
            style=self.zone_style,
            fill_alpha=self.zone_fill_alpha,
            spread_deg=self.zone_spread_deg,
            preview=False
        )
        self.scene.addItem(zone)
        self.zones.append(zone)

        # reset état création
        self.zone_points = []
        return True

    # ====== édition/suppression ======
    def cancel_zone(self):
        self.remove_zone_preview()
        self.zone_points = []

    def delete_selected_zone(self):
        if self.selected_zone:
            zone = self.selected_zone
            # Clean handles si tu en rajoutes plus tard (pas nécessaire ici)
            if zone in self.zones:
                self.zones.remove(zone)
            try:
                self.scene.removeItem(zone)
            except RuntimeError:
                pass
        self.clear_selection()