"""Thư viện sách + tiến độ: JSON trong thư mục dữ liệu của app.

Windows: %APPDATA%/VieNeuReader — sách được SAO CHÉP vào books/ để
không phụ thuộc file gốc; cache WAV theo hash nội dung trong cache/.
"""
import hashlib
import json
import os
import shutil
import time
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / "VieNeuReader"
    (d / "books").mkdir(parents=True, exist_ok=True)
    (d / "cache").mkdir(parents=True, exist_ok=True)
    return d


def _lib_path() -> Path:
    return data_dir() / "library.json"


def load_library() -> list[dict]:
    p = _lib_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return []


def save_library(books: list[dict]) -> None:
    _lib_path().write_text(json.dumps(books, ensure_ascii=False, indent=1), "utf-8")


def add_book(src_path: str, meta: dict) -> dict:
    src = Path(src_path)
    book_id = hashlib.sha1(f"{src.name}|{src.stat().st_size}|{time.time()}".encode()).hexdigest()[:12]
    dest = data_dir() / "books" / f"{book_id}{src.suffix.lower()}"
    shutil.copy2(src, dest)
    book = {
        "id": book_id, "title": meta.get("title") or src.stem,
        "author": meta.get("author") or "", "format": src.suffix.lower().lstrip("."),
        "file": str(dest), "paragraphs": meta["paragraphs"],
        "item": 0, "voice": "", "added": int(time.time()),
    }
    books = load_library()
    books.append(book)
    save_library(books)
    return book


def update_book(book: dict) -> None:
    books = load_library()
    for i, b in enumerate(books):
        if b["id"] == book["id"]:
            books[i] = book
            break
    save_library(books)


def remove_book(book_id: str) -> None:
    books = [b for b in load_library() if b["id"] != book_id]
    save_library(books)
    f = data_dir() / "books"
    for p in f.glob(f"{book_id}.*"):
        p.unlink(missing_ok=True)
    cache = data_dir() / "cache" / book_id
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)


def cache_path(book_id: str, text: str, voice: str, precision: str) -> Path:
    h = hashlib.sha256(f"{voice}|{precision}|{text}".encode("utf-8")).hexdigest()[:24]
    d = data_dir() / "cache" / book_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.wav"


def add_web_book(first: dict) -> dict:
    """Tạo sách web từ chương đầu tiên đã tải (first = webfetch.fetch_chapter)."""
    book_id = hashlib.sha1(f"web|{first['url']}|{time.time()}".encode()).hexdigest()[:12]
    book = {
        "id": book_id, "title": first.get("title") or "Truyện web",
        "author": "", "format": "web", "file": "",
        "paragraphs": first["paragraphs"], "item": 0, "voice": "",
        "added": int(time.time()),
        "web": {"next_url": first.get("next_url", ""),
                "chapters": [{"title": first.get("title") or "Chương 1", "para": 0}]},
    }
    books = load_library()
    books.append(book)
    save_library(books)
    return book
