"""Native disclosure sections and compact scene rows for the studio workspace."""
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QFont, QIcon, QImageReader, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFormLayout,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from .theme import THEMES

MOTION_LABELS = {
    'static': 'Still', 'slow_zoom_in': 'Slow zoom in', 'slow_zoom_out': 'Slow zoom out',
    'pan_left': 'Pan left', 'pan_right': 'Pan right', 'parallax': 'Parallax',
}
TRANSITION_LABELS = {'cut': 'Cut', 'crossfade': 'Crossfade', 'fade_black': 'Fade to black'}


class FormSection(QWidget):
    """Hide infrequent settings without replacing their widgets or values."""
    def __init__(self, title, *, expanded=True, stacked=False):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.theme = 'light'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle = QPushButton(title)
        self.toggle.setProperty('variant', 'section')
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setIconSize(QSize(12, 12))
        self.toggle.setToolTip('Show or hide ' + title.lower() + ' settings.')
        layout.addWidget(self.toggle)
        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setContentsMargins(0, 0, 0, 12)
        self.form.setVerticalSpacing(8)
        self.form.setHorizontalSpacing(16)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        if stacked:
            self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        layout.addWidget(self.body)
        self.toggle.toggled.connect(self._toggled)
        self._toggled(expanded)

    def set_expanded(self, expanded):
        self.toggle.setChecked(expanded)

    def set_theme(self, theme):
        self.theme = theme
        self._update_icon()

    def _toggled(self, expanded):
        self.body.setVisible(expanded)
        self._update_icon()
        self.updateGeometry()

    def _update_icon(self):
        pixmap = QPixmap(str(Path(__file__).with_name('theme_assets') / f'{self.theme}-down.png'))
        if not self.toggle.isChecked():
            pixmap = pixmap.transformed(QTransform().rotate(-90))
        self.toggle.setIcon(QIcon(pixmap))


class ThumbnailCache:
    """Bound image decoding and invalidate when an asset changes on disk."""
    def __init__(self, limit=128):
        self.limit = limit
        self.images = OrderedDict()

    def get(self, path):
        if path is None:
            return QPixmap()
        try:
            stat = path.stat()
        except OSError:
            return QPixmap()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        if key not in self.images:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(size.scaled(QSize(96, 144), Qt.AspectRatioMode.KeepAspectRatio))
            self.images[key] = QPixmap.fromImage(reader.read())
            while len(self.images) > self.limit:
                self.images.popitem(last=False)
        self.images.move_to_end(key)
        return self.images[key]


class SceneListDelegate(QStyledItemDelegate):
    """Keep native selection/focus while giving scene artwork and text hierarchy."""
    def sizeHint(self, option, index):
        return QSize(190, 92)

    def paint(self, painter, option, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return super().paint(painter, option, index)
        background = QStyleOptionViewItem(option)
        self.initStyleOption(background, index)
        background.text = ''
        background.icon = QIcon()
        option.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, background, painter, option.widget)

        colors = THEMES[getattr(option.widget.window(), 'current_theme', 'light')]
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        foreground = colors['selection_text'] if selected else colors['text']
        secondary = colors['selection_text'] if selected else colors['muted']
        painter.save()
        painter.setClipRect(option.rect)
        image_rect = QRect(option.rect.left() + 10, option.rect.top() + 12, 44, 68)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, image_rect, Qt.AlignmentFlag.AlignCenter)
        text_rect = option.rect.adjusted(64, 10, -10, -8)
        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(foreground)
        painter.drawText(QRect(text_rect.left(), text_rect.top(), text_rect.width(), 22),
                         Qt.AlignmentFlag.AlignVCenter, data['title'])
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        excerpt = painter.fontMetrics().elidedText(data['excerpt'], Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(QRect(text_rect.left(), text_rect.top() + 24, text_rect.width(), 20),
                         Qt.AlignmentFlag.AlignVCenter, excerpt)
        painter.setPen(secondary)
        font.setPixelSize(12)
        painter.setFont(font)
        metadata = painter.fontMetrics().elidedText(data['metadata'], Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(QRect(text_rect.left(), text_rect.top() + 49, text_rect.width(), 20),
                         Qt.AlignmentFlag.AlignVCenter, metadata)
        painter.restore()
