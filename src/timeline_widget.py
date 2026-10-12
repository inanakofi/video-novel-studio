"""Native painted timeline with real waveforms, drag handles and a playhead."""
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget

from .settings import settings_for, card_durations
from .timeline import total_duration
from .theme import THEMES
from .ui_widgets import MOTION_LABELS, TRANSITION_LABELS


class TimelineWidget(QWidget):
    edited = Signal(str, int, float, float)
    selected = Signal(str, int)
    seek = Signal(float)
    TRACKS = {'scene': (28, 34), 'transition': (68, 16), 'voice': (92, 44),
              'music': (144, 20), 'effect': (173, 20), 'caption': (202, 34)}
    LABEL = 108

    def __init__(self, parent=None):
        super().__init__(parent)
        self.episode, self.cues, self.envelope = None, [], None
        self.effects = []
        self.duration, self.scale, self.playhead = 1, 28, 0
        self.blocks, self.drag, self.selection = [], None, None
        self.colors = THEMES['light']
        self.setMinimumHeight(245)
        self.setMouseTracking(True)
        self.setToolTip('Drag caption edges to trim or its middle to move. Drag scene/transition right edges. Drag sound effects to move. Click ruler or waveform to seek.')

    def set_data(self, episode, cues, envelope=None, effects=None):
        self.episode, self.cues, self.envelope = episode, list(cues), envelope
        self.effects = effects or []
        self.duration = total_duration(episode) if episode else 1
        self._layout()

    def set_theme(self, theme):
        self.colors = THEMES[theme]
        self._layout()

    def set_zoom(self, scale):
        self.scale = scale
        self._layout()

    def set_position(self, seconds):
        self.playhead = max(0, min(self.duration, seconds))
        self.update()

    def x_at(self, seconds):
        return self.LABEL + seconds * self.scale

    def seconds_at(self, x):
        return max(0, min(self.duration, (x - self.LABEL) / self.scale))

    def _layout(self):
        self.setMinimumWidth(round(self.x_at(self.duration) + 25))
        self.blocks = []
        if self.episode:
            settings = settings_for(self.episode)
            title, end = card_durations(settings)
            for i, timed in enumerate(self.episode.timeline()):
                start, stop = title + timed.start_seconds, title + timed.end_seconds
                self._block('scene', i, start, stop, f'{timed.scene.scene_id:02} · {MOTION_LABELS[timed.scene.camera_motion]}', self.colors['track_scene'])
                if timed.scene.transition != 'cut':
                    self._block('transition', i, start, start + min(timed.scene.transition_seconds, timed.scene.duration_seconds / 2), TRANSITION_LABELS[timed.scene.transition], self.colors['track_transition'])
            if title:
                self._block('card', -1, 0, title, 'Title', self.colors['track_card'], lane='scene')
            if end:
                self._block('card', -1, self.duration-end, self.duration, 'End', self.colors['track_card'], lane='scene')
            if settings['music_asset']:
                self._block('music', 0, 0, self.duration, f'Loop · {settings["music_volume"]:.0%} music', self.colors['track_music'])
            for i, effect in enumerate(self.effects):
                self._block('effect', i, effect['start_seconds'], effect['start_seconds'] + effect['duration'], effect['label'], self.colors['track_effect'])
            for i, cue in enumerate(self.cues):
                self._block('caption', i, cue.start, cue.end, cue.text.replace('\n', ' '), self.colors['track_caption'])
        self.update()

    def _block(self, kind, index, start, end, text, color, lane=None):
        y, height = self.TRACKS[lane or kind]
        self.blocks.append({'kind': kind, 'index': index, 'start': start, 'end': end,
                            'text': text, 'color': color,
                            'rect': QRectF(self.x_at(start), y, max(2, (end-start)*self.scale), height)})

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.colors['surface']))
        painter.setFont(QFont('Segoe UI', 9))
        left = max(0, int((event.rect().left() - self.LABEL) / self.scale))
        right = min(int(self.duration)+1, int((event.rect().right() - self.LABEL) / self.scale)+1)
        interval = 1 if self.scale >= 45 else 5
        for seconds in range(left - left % interval, right + 1, interval):
            x = self.x_at(seconds)
            painter.setPen(QColor(self.colors['timeline_grid']))
            painter.drawLine(int(x), 27, int(x), 241)
            painter.setPen(QColor(self.colors['muted']))
            painter.drawText(QRectF(x+3, 2, 70, 24), Qt.AlignmentFlag.AlignLeft, f'{seconds}s')
        for name, (y, height) in self.TRACKS.items():
            painter.setPen(QColor(self.colors['muted']))
            painter.drawText(QRectF(8, y, 95, height), Qt.AlignmentFlag.AlignVCenter, {'voice': 'Narration', 'effect': 'SFX', 'caption': 'Captions'}.get(name, name.title()))
        if self.envelope:
            y, height = self.TRACKS['voice']
            painter.setPen(QPen(QColor(self.colors['waveform']), 1))
            step = self.envelope['bin_seconds']
            peaks = self.envelope['peaks']
            start = max(0, int((event.rect().left()-self.LABEL)/self.scale/step))
            stop = min(len(peaks), int((event.rect().right()-self.LABEL)/self.scale/step)+1)
            stride = max(1, int(1/(self.scale*step)))
            for i in range(start, stop, stride):
                amplitude = max(peaks[i:min(i+stride, len(peaks))]) * height * .48
                x = self.x_at(i*step)
                painter.drawLine(int(x), int(y+height/2-amplitude), int(x), int(y+height/2+amplitude))
        else:
            painter.setPen(QColor(self.colors['muted']))
            painter.drawText(QRectF(self.LABEL+12, 92, 650, 44), 'Load waveform to hear current narration and correct caption timing.')
        for block in self.blocks:
            rect = block['rect']
            if not rect.intersects(QRectF(event.rect())):
                continue
            selected = self.selection == (block['kind'], block['index'])
            painter.setPen(QPen(QColor(self.colors['accent'] if selected else block['color']), 2 if selected else 1))
            painter.setBrush(QColor(block['color']))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
            painter.setPen(QColor(self.colors['track_text']))
            text = painter.fontMetrics().elidedText(block['text'], Qt.TextElideMode.ElideRight, max(0, int(rect.width()-12)))
            painter.drawText(rect.adjusted(6, 1, -4, -1), Qt.AlignmentFlag.AlignVCenter, text)
            if block['kind'] in ('scene', 'transition', 'caption'):
                painter.drawLine(int(rect.right()-4), int(rect.top()+6), int(rect.right()-4), int(rect.bottom()-6))
                if block['kind'] == 'caption':
                    painter.drawLine(int(rect.left()+4), int(rect.top()+6), int(rect.left()+4), int(rect.bottom()-6))
        painter.setPen(QPen(QColor(self.colors['playhead']), 2))
        x = self.x_at(self.playhead)
        painter.drawLine(int(x), 25, int(x), 241)
        if self.drag:
            painter.setPen(QColor(self.colors['playhead']))
            painter.drawText(QRectF(x+5, 4, 170, 20), f'{self.playhead:.3f}s')

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position()
        for block in reversed(self.blocks):
            if block['rect'].contains(point):
                self.selection = block['kind'], block['index']
                self.selected.emit(*self.selection)
                edge = 'move'
                if abs(point.x()-block['rect'].right()) <= 9:
                    edge = 'end'
                elif block['kind'] == 'caption' and abs(point.x()-block['rect'].left()) <= 9:
                    edge = 'start'
                if block['kind'] == 'caption' or block['kind'] == 'effect' or (block['kind'] in ('scene', 'transition') and edge == 'end'):
                    self.drag = {**block, 'edge': 'move' if block['kind'] == 'effect' else edge, 'anchor': point.x()}
                else:
                    self.seek.emit(self.seconds_at(point.x()))
                self.update()
                return
        seconds = self.seconds_at(point.x())
        self.set_position(seconds)
        self.seek.emit(seconds)

    def mouseMoveEvent(self, event):
        if not self.drag:
            return
        delta = (event.position().x() - self.drag['anchor']) / self.scale
        start, end = self.drag['start'], self.drag['end']
        if self.drag['edge'] in ('move', 'start'):
            start += delta
        if self.drag['edge'] in ('move', 'end'):
            end += delta
        self.drag['proposed'] = start, end
        self.set_position(start if self.drag['edge'] == 'start' else end)
        # Show proposed geometry while dragging; model changes only after validation.
        for block in self.blocks:
            if (block['kind'], block['index']) == self.selection:
                y, height = self.TRACKS[block['kind']]
                block['rect'] = QRectF(self.x_at(start), y, max(2, (end-start)*self.scale), height)
        self.update()

    def mouseReleaseEvent(self, event):
        if self.drag:
            drag, self.drag = self.drag, None
            if 'proposed' in drag:
                self.edited.emit(drag['kind'], drag['index'], *drag['proposed'])
            self._layout()
