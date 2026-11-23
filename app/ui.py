"""Cửa sổ chính: thư viện (trái) + trình đọc (phải) + thanh phát (đáy).
Phong cách: tối giản chức năng, panel kính mờ trên nền gradient tối."""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from . import extract, store
from .engine import EngineThread
from .player import Player
from .textnorm import build_playback_items

STYLE = """
QMainWindow, QWidget { background: #101613; color: #e8f0ec; font-family: 'Segoe UI'; font-size: 14px; }
QListWidget, QTextEdit, QComboBox, QSpinBox {
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  border-radius: 10px; padding: 6px;
}
QListWidget::item { padding: 8px; border-radius: 8px; }
QListWidget::item:selected { background: rgba(45,212,191,0.25); }
QPushButton {
  background: rgba(255,255,255,0.09); border: 1px solid rgba(255,255,255,0.14);
  border-radius: 10px; padding: 8px 14px;
}
QPushButton:hover { background: rgba(255,255,255,0.16); }
QPushButton#playBtn { background: #2dd4bf; color: #04211c; font-weight: 700; border: none; }
QLabel#statusLbl { color: #9db3aa; }
QTextEdit { line-height: 150%; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Đọc Sách VieNeu")
        self.resize(1180, 760)
        self.setStyleSheet(STYLE)

        self.engine = EngineThread()
        self.engine.ready.connect(self._on_voices)
        self.engine.failed.connect(lambda m: self.status_lbl.setText(m))
        self.engine.status.connect(lambda m: self.status_lbl.setText(m))
        self.engine.start()

        self.player = Player(self.engine)
        self.player.item_changed.connect(self._on_item)
        self.player.state_changed.connect(self._on_state)
        self.player.waiting.connect(lambda i: self.status_lbl.setText(f"Đang tổng hợp đoạn {i + 1}…"))

        self.book: dict | None = None
        self.items: list[dict] = []
        self.item_ranges: list[tuple[int, int]] = []
        self._save_timer = QTimer(self, singleShot=True, interval=4000)
        self._save_timer.timeout.connect(self._flush_progress)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        # --- Thư viện ---
        side = QVBoxLayout()
        side.addWidget(QLabel("Thư viện"))
        self.book_list = QListWidget()
        self.book_list.itemClicked.connect(self._open_selected)
        side.addWidget(self.book_list, 1)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("＋ Thêm sách")
        add_btn.clicked.connect(self._add_books)
        del_btn = QPushButton("Xoá")
        del_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(add_btn, 1)
        btn_row.addWidget(del_btn)
        side.addLayout(btn_row)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(260)
        layout.addWidget(side_w)

        # --- Đọc + phát ---
        main = QVBoxLayout()
        top = QHBoxLayout()
        self.title_lbl = QLabel("Chọn một cuốn sách để bắt đầu")
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        top.addWidget(self.title_lbl, 1)
        top.addWidget(QLabel("Cỡ chữ"))
        self.font_spin = QSpinBox(minimum=13, maximum=26, value=17)
        self.font_spin.valueChanged.connect(self._apply_font)
        top.addWidget(self.font_spin)
        main.addLayout(top)

        self.reader = QTextEdit(readOnly=True)
        self.reader.mouseReleaseEvent = self._reader_clicked
        main.addWidget(self.reader, 1)

        bar = QHBoxLayout()
        prev_btn = QPushButton("⏮")
        prev_btn.clicked.connect(self.player.prev)
        self.play_btn = QPushButton("▶  Nghe")
        self.play_btn.setObjectName("playBtn")
        self.play_btn.clicked.connect(self.player.toggle)
        next_btn = QPushButton("⏭")
        next_btn.clicked.connect(self.player.next)
        bar.addWidget(prev_btn)
        bar.addWidget(self.play_btn)
        bar.addWidget(next_btn)
        bar.addWidget(QLabel("Giọng"))
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(170)
        self.voice_combo.currentIndexChanged.connect(self._voice_changed)
        bar.addWidget(self.voice_combo)
        bar.addWidget(QLabel("Tốc độ"))
        self.rate_combo = QComboBox()
        self.rate_combo.addItems(["0.75×", "0.9×", "1.0×", "1.1×", "1.25×", "1.5×"])
        self.rate_combo.setCurrentText("1.0×")
        self.rate_combo.currentTextChanged.connect(lambda t: self.player.set_rate(float(t.replace("×", ""))))
        bar.addWidget(self.rate_combo)
        bar.addWidget(QLabel("Chất lượng"))
        self.prec_combo = QComboBox()
        self.prec_combo.addItems(["int8 (nhanh)", "fp32 (xịn nhất)"])
        self.prec_combo.currentTextChanged.connect(
            lambda t: self.engine.set_precision("fp32" if t.startswith("fp32") else "int8"))
        bar.addWidget(self.prec_combo)
        self.pos_lbl = QLabel("")
        bar.addWidget(self.pos_lbl)
        main.addLayout(bar)

        self.status_lbl = QLabel("Engine VieNeu sẽ nạp khi bấm Nghe lần đầu.")
        self.status_lbl.setObjectName("statusLbl")
        main.addWidget(self.status_lbl)
        layout.addLayout(main, 1)

        self._reload_library()

    # ---------- thư viện ----------
    def _reload_library(self, select_id: str | None = None):
        self.book_list.clear()
        for b in store.load_library():
            label = b["title"] + (f" — {b['author']}" if b.get("author") else "")
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, b["id"])
            it.setToolTip(f"{b['format'].upper()} · đoạn {b.get('item', 0) + 1}")
            self.book_list.addItem(it)
            if select_id == b["id"]:
                self.book_list.setCurrentItem(it)

    def _add_books(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Thêm sách", "", "Sách (*.pdf *.epub *.txt)")
        last = None
        for f in files:
            try:
                meta = extract.extract(f)
                if not meta["paragraphs"]:
                    raise ValueError("Không bóc được chữ nào từ file này (PDF scan?)")
                last = store.add_book(f, meta)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Thêm sách lỗi", f"{Path(f).name}: {e}")
        self._reload_library(last["id"] if last else None)
        if last:
            self._open_book(last)

    def _remove_selected(self):
        it = self.book_list.currentItem()
        if not it:
            return
        if QMessageBox.question(self, "Xoá sách", "Xoá sách này khỏi thư viện?") == QMessageBox.StandardButton.Yes:
            store.remove_book(it.data(Qt.ItemDataRole.UserRole))
            if self.book and self.book["id"] == it.data(Qt.ItemDataRole.UserRole):
                self.book = None
                self.reader.clear()
                self.player.stop()
            self._reload_library()

    def _open_selected(self, item: QListWidgetItem):
        book_id = item.data(Qt.ItemDataRole.UserRole)
        for b in store.load_library():
            if b["id"] == book_id:
                self._open_book(b)
                return

    # ---------- mở sách ----------
    def _open_book(self, book: dict):
        self._flush_progress()
        self.book = book
        self.items = build_playback_items(book["paragraphs"])
        self.title_lbl.setText(book["title"])
        self._render_text()
        voice = book.get("voice") or ""
        self.player.load(book["id"], self.items, start=book.get("item", 0), voice=voice)
        self._highlight(book.get("item", 0), scroll=True)
        self.pos_lbl.setText(f"Đoạn {book.get('item', 0) + 1}/{len(self.items)}")
        self.status_lbl.setText("Bấm Nghe để đọc từ đoạn đã đánh dấu, hoặc bấm vào một câu để đọc từ đó.")

    def _render_text(self):
        self.reader.clear()
        self.item_ranges = []
        cursor = self.reader.textCursor()
        fmt = QTextCharFormat()
        para_starts = []
        for pi, para in enumerate(self.book["paragraphs"]):
            para_starts.append(cursor.position())
            cursor.insertText(para + "\n\n", fmt)
        # Ánh xạ từng đoạn phát -> khoảng ký tự trong tài liệu
        cursors: dict[int, int] = {}
        for item in self.items:
            pi = item["para"]
            start_at = cursors.get(pi, para_starts[pi])
            text = self.book["paragraphs"][pi]
            idx = text.find(item["text"][:40], start_at - para_starts[pi])
            if idx < 0:
                idx = text.find(item["text"][:20], start_at - para_starts[pi])
            if idx < 0:
                self.item_ranges.append((start_at, start_at))
                continue
            begin = para_starts[pi] + idx
            end = begin + len(item["text"])
            self.item_ranges.append((begin, min(end, para_starts[pi] + len(text))))
            cursors[pi] = end
        self._apply_font(self.font_spin.value())

    def _apply_font(self, px: int):
        font = QFont("Segoe UI", px)
        self.reader.setFont(font)

    def _highlight(self, index: int, scroll: bool = False):
        if not (0 <= index < len(self.item_ranges)):
            return
        begin, end = self.item_ranges[index]
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(45, 212, 191, 90))
        sel = QTextEdit.ExtraSelection()
        cur = QTextCursor(self.reader.document())
        cur.setPosition(begin)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        sel.cursor = cur
        sel.format = fmt
        self.reader.setExtraSelections([sel])
        if scroll:
            view_cur = QTextCursor(self.reader.document())
            view_cur.setPosition(begin)
            self.reader.setTextCursor(view_cur)
            self.reader.ensureCursorVisible()

    def _reader_clicked(self, event):
        QTextEdit.mouseReleaseEvent(self.reader, event)
        if not self.items:
            return
        pos = self.reader.textCursor().position()
        for i, (b, e) in enumerate(self.item_ranges):
            if b <= pos <= e:
                self.player.go(i)
                if not self.player.playing:
                    self.player.play()
                break

    # ---------- player callbacks ----------
    def _on_voices(self, voices: list):
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        for desc, vid in voices:
            self.voice_combo.addItem(desc or vid, vid)
        cur = self.book.get("voice") if self.book else ""
        if cur:
            ix = self.voice_combo.findData(cur)
            if ix >= 0:
                self.voice_combo.setCurrentIndex(ix)
        elif voices:
            self.player.set_voice(voices[0][1])
        self.voice_combo.blockSignals(False)

    def _voice_changed(self):
        vid = self.voice_combo.currentData()
        if vid:
            self.player.set_voice(vid)
            if self.book:
                self.book["voice"] = vid
                self._save_timer.start()

    def _on_item(self, index: int):
        self._highlight(index, scroll=True)
        self.pos_lbl.setText(f"Đoạn {index + 1}/{len(self.items)}")
        if self.book:
            self.book["item"] = index
            self._save_timer.start()

    def _on_state(self, playing: bool):
        self.play_btn.setText("⏸  Dừng" if playing else "▶  Nghe")

    def _flush_progress(self):
        if self.book:
            store.update_book(self.book)

    def closeEvent(self, event):
        self._flush_progress()
        self.engine.stop()
        self.engine.wait(1500)
        super().closeEvent(event)
