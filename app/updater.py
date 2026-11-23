"""Tự cập nhật trong app: kiểm tra GitHub Releases, tải zip bản mới,
chạy script ngoài để ghi đè thư mục cài đặt rồi mở lại app.

Chỉ áp dụng khi chạy bản đóng gói (sys.frozen). Script cập nhật (.bat)
nằm ở %TEMP% để không bị chính quá trình ghi đè khoá.
"""
import json
import re
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "hieuka001/vieneu-reader-pc"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
_UA = {"User-Agent": "VieNeuReader-Updater", "Accept": "application/vnd.github+json"}


def parse_version(text: str) -> tuple[int, int, int]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def parse_release(data: dict) -> dict:
    zip_url, size = "", 0
    for a in data.get("assets", []):
        if (a.get("name") or "").endswith(".zip"):
            zip_url = a.get("browser_download_url") or ""
            size = int(a.get("size") or 0)
            break
    return {"tag": data.get("tag_name") or "",
            "version": parse_version(data.get("tag_name") or ""),
            "zip_url": zip_url, "size": size,
            "notes": (data.get("body") or "")[:600],
            "html_url": data.get("html_url") or ""}


def check_latest(timeout: int = 12) -> dict:
    req = urllib.request.Request(API_LATEST, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_release(json.load(resp))


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    return Path(sys.executable).resolve().parent


def download(url: str, dest: Path, on_progress=None, chunk: int = 1 << 18) -> Path:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if on_progress:
                    on_progress(done, total)
    return dest


def apply_update(zip_path: Path) -> None:
    """Giải nén + sinh script cập nhật + khởi chạy nó (app tự thoát sau đó)."""
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="vnr-update-"))
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(work)
    src = work / "VieNeuReader"
    if not src.exists():  # zip không có thư mục gốc: lấy thư mục con đầu tiên chứa exe
        for p in work.rglob("VieNeuReader.exe"):
            src = p.parent
            break
    dst = install_dir()
    bat = work / "apply-update.bat"
    bat.write_text(
        "@echo off\r\n"
        f"set PID={os_getpid()}\r\n"
        ":wait\r\n"
        'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul && '
        "(ping -n 2 127.0.0.1 >nul & goto wait)\r\n"
        f'robocopy "{src}" "{dst}" /E /R:3 /W:1 >nul\r\n'
        f'start "" "{dst / "VieNeuReader.exe"}"\r\n',
        encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(bat)],
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                     close_fds=True)


def os_getpid() -> int:
    import os
    return os.getpid()
