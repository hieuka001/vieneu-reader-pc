"""Chuẩn hoá + tách câu tiếng Việt cho TTS.

Bài học từ Sách Nói Offline:
- Dấu ':' và ';' KHÔNG kết thúc câu.
- Câu dài phải chẻ nhỏ ở ranh giới mệnh đề (<= ~180 ký tự) để engine
  tổng hợp nhanh, không bắt người nghe chờ cả câu dài.
- Chữ viết hoa đọc nguyên từ (engine tự xử lý), chỉ dọn khoảng trắng.
"""
import re

_CLAUSE_BREAK = re.compile(r"(?<=[,;:—–])\s+|\s+-\s+")
_SENT_END = re.compile(r"(?<=[.!?…])\s+|(?<=[.!?…])[\"”’»)]\s+|\n{2,}")


def clean_text(text: str) -> str:
    text = text.replace("​", "").replace("\ufeff", "")
    text = text.replace("§", " mục ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(paragraph: str) -> list[str]:
    parts = [p.strip() for p in _SENT_END.split(paragraph) if p and p.strip()]
    # split() bỏ mất dấu kết câu nằm ở lookbehind khi dùng alternation thứ hai;
    # chấp nhận được cho TTS (engine tự ngắt hơi theo ngữ cảnh).
    return parts


def chunk_sentence(sentence: str, max_chars: int = 180) -> list[str]:
    sentence = sentence.strip()
    if len(sentence) <= max_chars:
        return [sentence] if sentence else []
    pieces = _CLAUSE_BREAK.split(sentence)
    chunks, cur = [], ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if len(piece) > max_chars:  # mệnh đề vẫn quá dài: cắt theo khoảng trắng
            words = piece.split()
            for w in words:
                if len(cur) + len(w) + 1 > max_chars and cur:
                    chunks.append(cur.strip())
                    cur = w
                else:
                    cur = (cur + " " + w).strip()
            continue
        if len(cur) + len(piece) + 1 > max_chars and cur:
            chunks.append(cur.strip())
            cur = piece
        else:
            cur = (cur + " " + piece).strip() if cur else piece
    if cur.strip():
        chunks.append(cur.strip())
    return [c for c in chunks if len(c) >= 2 or c.isdigit()]


def build_playback_items(paragraphs: list[str], max_chars: int = 180) -> list[dict]:
    """Trả danh sách đoạn phát: {para: chỉ số đoạn, text: câu/đoạn đã chẻ}."""
    items = []
    for pi, para in enumerate(paragraphs):
        for sent in split_sentences(para):
            for chunk in chunk_sentence(sent, max_chars):
                items.append({"para": pi, "text": chunk})
    return items
