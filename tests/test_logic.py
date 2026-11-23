import sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.textnorm import build_playback_items, split_sentences, chunk_sentence
from app import extract


def test_colon_semicolon_not_sentence_end():
    s = split_sentences("Lão Tử nói: đạo khả đạo. Danh khả danh; phi thường danh!")
    assert s[0].startswith("Lão Tử nói:")
    assert any("phi thường danh" in x for x in s)


def test_long_sentence_chunked():
    chunks = chunk_sentence("Một câu dài, " * 30 + "hết.", 180)
    assert len(chunks) > 1
    assert all(len(c) <= 190 for c in chunks)


def test_items_map_to_paragraphs():
    items = build_playback_items(["Đoạn một. Câu hai.", "Đoạn hai ở đây."])
    assert items[0]["para"] == 0 and items[-1]["para"] == 1
    assert len(items) == 3


def test_extract_txt(tmp_path):
    p = tmp_path / "sach.txt"
    p.write_text("Chương 1 mở đầu.\n\nNội dung đoạn một ở đây.\n\nĐoạn hai tiếp theo.", encoding="utf-8")
    meta = extract.extract_txt(str(p))
    assert len(meta["paragraphs"]) == 3


def test_extract_epub(tmp_path):
    p = tmp_path / "sach.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf",
                   '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf">'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   '<dc:title>Sách Test</dc:title><dc:creator>Tác Giả</dc:creator></metadata>'
                   '<manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest>'
                   '<spine><itemref idref="c1"/></spine></package>')
        z.writestr("OEBPS/c1.xhtml",
                   "<html><body><h1>Chương 1</h1><p>Xin chào thế giới.</p><p>Đoạn hai.</p></body></html>")
    meta = extract.extract_epub(str(p))
    assert meta["title"] == "Sách Test"
    assert any("Xin chào thế giới" in x for x in meta["paragraphs"])
