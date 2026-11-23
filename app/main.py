"""Điểm vào: GUI hoặc --selftest <report.json> (kiểm tra engine headless)."""
import io
import json
import os
import sys
import time
from pathlib import Path


def _ensure_streams():
    """Bản exe --windowed không có console: sys.stdout/stderr là None,
    thư viện nào ghi log/thanh tiến trình (HF download, tqdm...) sẽ sập
    với "'NoneType' object has no attribute 'write'". Trỏ chúng vào devnull."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stdin is None:
        sys.stdin = io.StringIO("")


def selftest(report_path: str) -> int:
    _ensure_streams()
    report = {"ok": False}
    try:
        t0 = time.time()
        from vieneu import Vieneu
        tts = Vieneu(precision="int8")
        report["load_s"] = round(time.time() - t0, 1)
        voices = tts.list_preset_voices()
        report["voices"] = len(voices)
        text = "Xin chào, đây là bản kiểm tra của ứng dụng Đọc Sách VieNeu."
        t1 = time.time()
        audio = tts.infer(text, voice=voices[0][1] if voices else None)
        synth_s = time.time() - t1
        dur = len(audio) / tts.sample_rate
        report.update({"synth_s": round(synth_s, 2), "audio_s": round(dur, 2),
                       "rtf": round(synth_s / dur, 3) if dur else None,
                       "sample_rate": tts.sample_rate})
        out_wav = str(Path(report_path).with_suffix(".wav"))
        tts.save(audio, out_wav)
        report["wav"] = out_wav
        report["ok"] = bool(dur > 0.5 and report["rtf"] is not None and report["rtf"] < 1.5)
    except Exception as e:  # noqa: BLE001
        import traceback
        report["error"] = f"{type(e).__name__}: {e}"
        report["traceback"] = traceback.format_exc()
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


def main() -> int:
    _ensure_streams()
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        report = sys.argv[i + 1] if i + 1 < len(sys.argv) else "selftest-report.json"
        return selftest(report)
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
