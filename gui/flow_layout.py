# gui/flow_layout.py
# Adapted from the official Qt C++ FlowLayout example

from PySide6.QtWidgets import QLayout, QStyle
from PySide6.QtCore import Qt, QRect, QPoint, QSize

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._item_list = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margin, _, _, _ = self.getContentsMargins()
        size += QSize(2 * margin, 2 * margin)
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self._item_list:
            style = self.parentWidget().style() or QStyle()
            spacing_x = self.spacing()
            spacing_y = self.spacing()
            if spacing_x == -1:
                spacing_x = style.layoutSpacing(Qt.Horizontal, Qt.Horizontal, Qt.Widget)
            if spacing_y == -1:
                spacing_y = style.layoutSpacing(Qt.Vertical, Qt.Vertical, Qt.Widget)

            next_x = x + item.sizeHint().width() + spacing_x
            if next_x - spacing_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing_y
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = x + item.sizeHint().width() + spacing_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()
