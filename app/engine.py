"""Engine VieNeu chạy trong thread riêng: nạp model lười (lần đầu tải
model từ HuggingFace), tổng hợp theo hàng đợi, cache WAV theo nội dung.

API theo SDK chính thức (vieneu 3.8.x, v3 Turbo):
    tts = Vieneu(precision="int8")     # CPU -> ONNX, không cần torch
    voices = tts.list_preset_voices()  # [(mô tả, voice_id)]
    audio = tts.infer(text, voice=voice_id)   # np.float32 @ sample_rate
    tts.save(audio, path)
"""
import queue
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import store


class EngineThread(QThread):
    ready = Signal(list)          # danh sách giọng [(desc, voice_id)]
    chunk_ready = Signal(int, str)  # (item_index, wav_path)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, precision: str = "int8"):
        super().__init__()
        self.precision = precision
        self._jobs: queue.Queue = queue.Queue()
        self._tts = None
        self._stop = False
        self._lock = threading.Lock()

    def request_synth(self, book_id: str, index: int, text: str, voice: str) -> None:
        path = store.cache_path(book_id, text, voice, self.precision)
        if path.exists() and path.stat().st_size > 1000:
            self.chunk_ready.emit(index, str(path))
            return
        self._jobs.put((book_id, index, text, voice, path))

    def set_precision(self, precision: str) -> None:
        if precision != self.precision:
            self.precision = precision
            self._tts = None  # nạp lại ở job kế tiếp

    def stop(self) -> None:
        self._stop = True
        self._jobs.put(None)

    def _ensure_engine(self) -> bool:
        if self._tts is not None:
            return True
        try:
            self.status.emit("Đang nạp engine VieNeu (lần đầu sẽ tải model, chờ một chút)…")
            from vieneu import Vieneu
            self._tts = Vieneu(precision=self.precision)
            voices = [(d, v) for d, v in self._tts.list_preset_voices()]
            self.status.emit("Engine VieNeu đã sẵn sàng")
            self.ready.emit(voices)
            return True
        except Exception as e:  # noqa: BLE001 - báo lỗi cho UI
            self.failed.emit(f"Không nạp được engine VieNeu: {e}")
            return False

    def run(self) -> None:
        while not self._stop:
            job = self._jobs.get()
            if job is None:
                break
            book_id, index, text, voice, path = job
            if path.exists() and path.stat().st_size > 1000:
                self.chunk_ready.emit(index, str(path))
                continue
            if not self._ensure_engine():
                continue
            try:
                audio = self._tts.infer(text, voice=voice or None)
                tmp = path.with_suffix(".tmp.wav")
                self._tts.save(audio, str(tmp))
                tmp.replace(path)
                self.chunk_ready.emit(index, str(path))
            except Exception as e:  # noqa: BLE001
                self.failed.emit(f"Tổng hợp lỗi ở đoạn {index + 1}: {e}")
