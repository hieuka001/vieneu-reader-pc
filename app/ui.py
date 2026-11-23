"""Cửa sổ chính: thư viện (trái) + [Đọc sách | Web truyện] (phải) + thanh phát (đáy).

- Đọc sách: PDF/EPUB/TXT + truyện web dán link.
- Web truyện: trình duyệt nhúng (đăng nhập Sáng Tác Việt..., cookie được lưu),
  bấm "Đọc chương này" để VieNeu đọc; hết chương tự bấm chương tiếp trên trang.
"""
import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QSpinBox, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from . import extract, store, webfetch
from .engine import EngineThread
from .player import Player
from .textnorm import build_playback_items
from .webview_js import EXTRACT_JS, NEXT_JS

STYLE = """
QMainWindow, QWidget { background: #101613; color: #e8f0ec; font-family: 'Segoe UI'; font-size: 14px; }
QListWidget, QTextEdit, QComboBox, QSpinBox, QLineEdit {
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
QPushButton:checked { background: rgba(45,212,191,0.35); }
QPushButton#playBtn { background: #2dd4bf; color: #04211c; font-weight: 700; border: none; }
QLabel#statusLbl { color: #9db3aa; }
"""

HOME_URL = "https://sangtacviet.com/"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Đọc Sách VieNeu")
        self.resize(1220, 800)
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
        self.player.finished.connect(self._on_finished)

        self.book: dict | None = None
        self.items: list[dict] = []
        self.item_ranges: list[tuple[int, int]] = []
        self._last_chapter_sig = ""
        self._poll_left = 0
        self._save_timer = QTimer(self, singleShot=True, interval=4000)
        self._save_timer.timeout.connect(self._flush_progress)
        self._poll_timer = QTimer(self, interval=1500)
        self._poll_timer.timeout.connect(self._poll_next_chapter)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        # ---------- Thư viện (trái) ----------
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
        web_btn = QPushButton("🌐 Thêm truyện bằng link")
        web_btn.clicked.connect(self._add_web)
        side.addWidget(web_btn)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(260)
        layout.addWidget(side_w)

        # ---------- Vùng phải ----------
        main = QVBoxLayout()
        toggle = QHBoxLayout()
        self.view_book_btn = QPushButton("📖 Đọc sách")
        self.view_book_btn.setCheckable(True)
        self.view_book_btn.setChecked(True)
        self.view_book_btn.clicked.connect(lambda: self._switch_view(0))
        self.view_web_btn = QPushButton("🌐 Web truyện")
        self.view_web_btn.setCheckable(True)
        self.view_web_btn.clicked.connect(lambda: self._switch_view(1))
        toggle.addWidget(self.view_book_btn)
        toggle.addWidget(self.view_web_btn)
        toggle.addStretch(1)
        main.addLayout(toggle)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_reader_page())
        self.stack.addWidget(self._build_browser_page())
        main.addWidget(self.stack, 1)

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
        self.rate_combo.addItems(["0.25×", "0.5×", "0.75×", "0.9×", "1.0×", "1.1×", "1.25×", "1.5×", "2.0×", "2.5×", "3.0×"])
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

    # ---------- các trang ----------
    def _build_reader_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        top = QHBoxLayout()
        self.title_lbl = QLabel("Chọn một cuốn sách, hoặc sang tab Web truyện")
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        top.addWidget(self.title_lbl, 1)
        top.addWidget(QLabel("Cỡ chữ"))
        self.font_spin = QSpinBox(minimum=13, maximum=26, value=17)
        self.font_spin.valueChanged.connect(self._apply_font)
        top.addWidget(self.font_spin)
        v.addLayout(top)

        self.reader = QTextEdit(readOnly=True)
        self.reader.mouseReleaseEvent = self._reader_clicked
        v.addWidget(self.reader, 1)

        chapter_bar = QHBoxLayout()
        chapter_bar.addWidget(QLabel("Chương"))
        self.chapter_combo = QComboBox()
        self.chapter_combo.setMinimumWidth(260)
        self.chapter_combo.currentIndexChanged.connect(self._chapter_selected)
        chapter_bar.addWidget(self.chapter_combo, 1)
        self.next_ch_btn = QPushButton("⬇ Tải chương tiếp")
        self.next_ch_btn.clicked.connect(self._fetch_next_chapter)
        chapter_bar.addWidget(self.next_ch_btn)
        self.chapter_widget = QWidget()
        self.chapter_widget.setLayout(chapter_bar)
        self.chapter_widget.setVisible(False)
        v.addWidget(self.chapter_widget)
        return page

    def _build_browser_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        nav = QHBoxLayout()
        back_btn = QPushButton("◀")
        back_btn.setFixedWidth(42)
        fwd_btn = QPushButton("▶")
        fwd_btn.setFixedWidth(42)
        reload_btn = QPushButton("⟳")
        reload_btn.setFixedWidth(42)
        self.address = QLineEdit(HOME_URL)
        self.address.returnPressed.connect(lambda: self.webview.load(QUrl(self.address.text().strip())))
        nav.addWidget(back_btn)
        nav.addWidget(fwd_btn)
        nav.addWidget(reload_btn)
        nav.addWidget(self.address, 1)
        v.addLayout(nav)

        profile = QWebEngineProfile("VieNeuWeb", self)
        profile.setPersistentStoragePath(str(store.data_dir() / "webprofile"))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.webview = QWebEngineView()
        self.webview.setPage(QWebEnginePage(profile, self.webview))
        self.webview.load(QUrl(HOME_URL))
        self.webview.urlChanged.connect(lambda u: self.address.setText(u.toString()))
        back_btn.clicked.connect(self.webview.back)
        fwd_btn.clicked.connect(self.webview.forward)
        reload_btn.clicked.connect(self.webview.reload)
        v.addWidget(self.webview, 1)

        bottom = QHBoxLayout()
        read_btn = QPushButton("▶ Đọc chương này")
        read_btn.setObjectName("playBtn")
        read_btn.clicked.connect(self._read_current_page)
        bottom.addWidget(read_btn)
        self.auto_next_chk = QCheckBox("Hết chương tự qua chương tiếp")
        self.auto_next_chk.setChecked(True)
        bottom.addWidget(self.auto_next_chk)
        bottom.addStretch(1)
        bottom.addWidget(QLabel("Đăng nhập 1 lần — app tự nhớ. Mở truyện, vào chương, bấm Đọc chương này."))
        v.addLayout(bottom)
        return page

    def _switch_view(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.view_book_btn.setChecked(idx == 0)
        self.view_web_btn.setChecked(idx == 1)

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
        files, _ = QFileDialog.getOpenFileNames(self, "Thêm sách", "", "Sách (*.pdf *.epub *.txt)")
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
            book_id = it.data(Qt.ItemDataRole.UserRole)
            store.remove_book(book_id)
            if self.book and self.book["id"] == book_id:
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

    # ---------- mở sách / hiển thị ----------
    def _open_book(self, book: dict):
        self._flush_progress()
        self.book = book
        self.items = build_playback_items(book["paragraphs"])
        self.title_lbl.setText(book["title"])
        self._render_text()
        self.player.load(book["id"], self.items, start=book.get("item", 0), voice=book.get("voice") or "")
        self._highlight(book.get("item", 0), scroll=True)
        self.pos_lbl.setText(f"Đoạn {book.get('item', 0) + 1}/{len(self.items)}")
        self._refresh_chapter_bar()
        self._switch_view(0)
        web = book.get("web") or {}
        last_ch = (web.get("chapters") or [{}])[-1]
        self._last_chapter_sig = (last_ch.get("title") or "") + "|" + (book["paragraphs"][last_ch.get("para", 0)] if book["paragraphs"] else "")
        self.status_lbl.setText("Bấm Nghe để đọc tiếp, hoặc bấm vào một câu để đọc từ đó.")

    def _render_text(self):
        self.reader.clear()
        self.item_ranges = []
        cursor = self.reader.textCursor()
        fmt = QTextCharFormat()
        para_starts = []
        for para in self.book["paragraphs"]:
            para_starts.append(cursor.position())
            cursor.insertText(para + "\n\n", fmt)
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
        self.reader.setFont(QFont("Segoe UI", px))

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

    # ---------- chương (sách web) ----------
    def _refresh_chapter_bar(self):
        web = (self.book or {}).get("web")
        self.chapter_widget.setVisible(bool(web))
        if not web:
            return
        self.chapter_combo.blockSignals(True)
        self.chapter_combo.clear()
        for ch in web["chapters"]:
            self.chapter_combo.addItem(ch["title"])
        if web.get("live"):
            self.next_ch_btn.setEnabled(True)
            self.next_ch_btn.setText("⬇ Qua chương tiếp (trên web)")
        else:
            self.next_ch_btn.setEnabled(bool(web.get("next_url")))
            self.next_ch_btn.setText("⬇ Tải chương tiếp" if web.get("next_url") else "Đã hết chương")
        self.chapter_combo.blockSignals(False)

    def _chapter_selected(self, idx: int):
        web = (self.book or {}).get("web")
        if not web or not (0 <= idx < len(web["chapters"])):
            return
        para = web["chapters"][idx]["para"]
        for i, it in enumerate(self.items):
            if it["para"] >= para:
                self.player.go(i)
                self._highlight(i, scroll=True)
                break

    def _append_chapter(self, chapter: dict, jump_to_new: bool = False):
        """Nối 1 chương vào sách hiện tại; giữ nguyên vị trí đang nghe trừ khi jump_to_new."""
        book = self.book
        was_playing = self.player.playing
        cur = self.player.index
        start_para = len(book["paragraphs"])
        first_new_item = len(self.items)
        book["paragraphs"].extend(chapter["paragraphs"])
        book["web"]["chapters"].append({"title": chapter.get("title") or "Chương tiếp", "para": start_para})
        if "next_url" in chapter:
            book["web"]["next_url"] = chapter.get("next_url", "")
        store.update_book(book)
        self._last_chapter_sig = (chapter.get("title") or "") + "|" + (chapter["paragraphs"][0] if chapter["paragraphs"] else "")
        self.items = build_playback_items(book["paragraphs"])
        self._render_text()
        target = first_new_item if jump_to_new else cur
        self.player.load(book["id"], self.items, start=target, voice=book.get("voice") or "")
        self._highlight(target, scroll=jump_to_new)
        self.pos_lbl.setText(f"Đoạn {target + 1}/{len(self.items)}")
        self._refresh_chapter_bar()
        if was_playing or jump_to_new:
            self.player.go(target)
            self.player.play()

    # ---------- truyện web bằng link ----------
    def _add_web(self):
        url, ok = QInputDialog.getText(self, "Thêm truyện bằng link", "Dán link chương đầu tiên (hoặc chương bất kỳ):")
        if not ok or not url.strip():
            return
        self.status_lbl.setText("Đang tải chương từ web…")
        self._fetch = FetchThread(url.strip())
        self._fetch.done.connect(self._web_added)
        self._fetch.failed.connect(lambda m: self.status_lbl.setText(m))
        self._fetch.start()

    def _web_added(self, first: dict):
        book = store.add_web_book(first)
        self._reload_library(book["id"])
        self._open_book(book)
        self.status_lbl.setText("Đã thêm truyện web. Nghe hết chương thì bấm 'Tải chương tiếp'.")

    def _fetch_next_chapter(self):
        web = (self.book or {}).get("web")
        if not web:
            return
        if web.get("live"):
            self._advance_web_chapter()
            return
        if not web.get("next_url"):
            return
        self.next_ch_btn.setEnabled(False)
        self.status_lbl.setText("Đang tải chương tiếp…")
        self._fetch = FetchThread(web["next_url"])
        self._fetch.done.connect(lambda ch: self._append_chapter(ch))
        self._fetch.failed.connect(lambda m: (self.status_lbl.setText(m), self._refresh_chapter_bar()))
        self._fetch.start()

    # ---------- web truyện nhúng (Sáng Tác Việt...) ----------
    def _read_current_page(self):
        self.status_lbl.setText("Đang bóc nội dung chương trên trang…")
        self.webview.page().runJavaScript(EXTRACT_JS, self._on_page_extracted)

    def _on_page_extracted(self, result):
        try:
            data = json.loads(result) if isinstance(result, str) else {}
        except Exception:  # noqa: BLE001
            data = {}
        paras = [p for p in data.get("paras", []) if len(p.strip()) >= 2]
        if len(paras) < 3:
            self.status_lbl.setText("Chưa bóc được nội dung — hãy mở hẳn vào trang đọc chương rồi bấm lại.")
            return
        first = {"title": data.get("title") or "Truyện web", "url": self.webview.url().toString(),
                 "paragraphs": paras, "next_url": ""}
        book = store.add_web_book(first)
        book["web"]["live"] = True
        store.update_book(book)
        self._reload_library(book["id"])
        self._open_book(book)
        self.player.play()
        self.status_lbl.setText("Đang đọc chương này. Hết chương app tự bấm chương tiếp trên trang web.")

    def _on_finished(self):
        web = (self.book or {}).get("web") or {}
        if web.get("live") and self.auto_next_chk.isChecked():
            self._advance_web_chapter()

    def _advance_web_chapter(self):
        self.status_lbl.setText("Đã hết chương — đang bấm chương tiếp trên trang web…")
        self.webview.page().runJavaScript(NEXT_JS, self._on_next_clicked)

    def _on_next_clicked(self, result):
        if result == "clicked":
            self._poll_left = 20
            self._poll_timer.start()
        else:
            self.status_lbl.setText("Không thấy nút 'chương sau' trên trang — anh bấm qua chương trên web rồi bấm 'Đọc chương này'.")

    def _poll_next_chapter(self):
        self._poll_left -= 1
        if self._poll_left <= 0:
            self._poll_timer.stop()
            self.status_lbl.setText("Trang chưa đổi chương — thử bấm qua chương thủ công trên web.")
            return
        self.webview.page().runJavaScript(EXTRACT_JS, self._check_new_chapter)

    def _check_new_chapter(self, result):
        if not self._poll_timer.isActive():
            return
        try:
            data = json.loads(result) if isinstance(result, str) else {}
        except Exception:  # noqa: BLE001
            return
        paras = [p for p in data.get("paras", []) if len(p.strip()) >= 2]
        if len(paras) < 3:
            return
        sig = (data.get("title") or "") + "|" + paras[0]
        if sig == self._last_chapter_sig:
            return  # trang chưa đổi nội dung
        self._poll_timer.stop()
        self._append_chapter({"title": data.get("title") or "Chương tiếp", "paragraphs": paras},
                             jump_to_new=True)
        self.status_lbl.setText("Đã qua chương mới, đang đọc tiếp.")

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


class FetchThread(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.done.emit(webfetch.fetch_chapter(self.url))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Tải web lỗi: {e}")
