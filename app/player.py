"""Điều khiển phát: QMediaPlayer + render trước 2 đoạn (prefetch),
tự sang đoạn kế khi hết, tô sáng qua signal cho UI."""
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from .engine import EngineThread

PREFETCH = 2


class Player(QObject):
    item_changed = Signal(int)       # đoạn đang phát thay đổi
    state_changed = Signal(bool)     # True = đang phát
    waiting = Signal(int)            # đang chờ tổng hợp đoạn này

    def __init__(self, engine: EngineThread):
        super().__init__()
        self.engine = engine
        self.audio = QAudioOutput()
        self.media = QMediaPlayer()
        self.media.setAudioOutput(self.audio)
        self.media.mediaStatusChanged.connect(self._on_status)
        engine.chunk_ready.connect(self._on_chunk)

        self.items: list[dict] = []
        self.book_id = ""
        self.voice = ""
        self.index = 0
        self.playing = False
        self._ready_files: dict[int, str] = {}
        self._want_play = False

    # --- nạp sách ---
    def load(self, book_id: str, items: list[dict], start: int = 0, voice: str = ""):
        self.stop()
        self.book_id = book_id
        self.items = items
        self.voice = voice
        self.index = max(0, min(start, max(0, len(items) - 1)))
        self._ready_files = {}

    def set_voice(self, voice: str):
        self.voice = voice
        self._ready_files = {}
        if self.playing:
            self._request(self.index)
            self._prefetch()

    def set_rate(self, rate: float):
        self.media.setPlaybackRate(rate)

    # --- điều khiển ---
    def play(self):
        if not self.items:
            return
        self.playing = True
        self._want_play = True
        self.state_changed.emit(True)
        self._request(self.index)
        self._prefetch()
        if self.index in self._ready_files:
            self._play_current()

    def pause(self):
        self.playing = False
        self._want_play = False
        self.media.pause()
        self.state_changed.emit(False)

    def stop(self):
        self.playing = False
        self._want_play = False
        self.media.stop()
        self.state_changed.emit(False)

    def toggle(self):
        self.pause() if self.playing else self.play()

    def go(self, index: int):
        if not self.items:
            return
        self.index = max(0, min(index, len(self.items) - 1))
        self.item_changed.emit(self.index)
        if self.playing:
            self._request(self.index)
            self._prefetch()
            if self.index in self._ready_files:
                self._play_current()
            else:
                self.media.stop()

    def next(self):
        self.go(self.index + 1)

    def prev(self):
        self.go(self.index - 1)

    # --- nội bộ ---
    def _request(self, index: int):
        if 0 <= index < len(self.items) and index not in self._ready_files:
            self.engine.request_synth(self.book_id, index, self.items[index]["text"], self.voice)

    def _prefetch(self):
        for k in range(1, PREFETCH + 1):
            self._request(self.index + k)

    def _on_chunk(self, index: int, path: str):
        self._ready_files[index] = path
        if self.playing and index == self.index and self._want_play:
            self._play_current()

    def _play_current(self):
        path = self._ready_files.get(self.index)
        if not path:
            self.waiting.emit(self.index)
            return
        self.item_changed.emit(self.index)
        self.media.setSource(QUrl.fromLocalFile(path))
        self.media.play()

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.playing:
            if self.index + 1 < len(self.items):
                self.index += 1
                self.item_changed.emit(self.index)
                self._prefetch()
                if self.index in self._ready_files:
                    self._play_current()
                else:
                    self.waiting.emit(self.index)
            else:
                self.stop()
