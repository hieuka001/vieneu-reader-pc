"""Bóc text từ PDF / EPUB / TXT thành danh sách đoạn (paragraphs).

- PDF: PyMuPDF; chương theo TOC nếu có (chỉ để hiển thị), đoạn = block text.
- EPUB: zipfile + XML, giữ thứ tự spine, đoạn theo thẻ <p>/<h*>/<li>/<br>.
- TXT: tách chương theo dòng tiêu đề (Chương/Chapter/Phần...), đoạn theo dòng trống.
"""
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .textnorm import clean_text

_HEADING_RE = re.compile(
    r"^\s*(chương|chuong|chapter|phần|phan|mục|hồi)\s+[\divxIVX0-9]+\b.*$",
    re.IGNORECASE,
)


def extract(path: str) -> dict:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".epub":
        return extract_epub(path)
    if ext == ".txt":
        return extract_txt(path)
    raise ValueError(f"Chưa hỗ trợ định dạng {ext}")


def extract_pdf(path: str) -> dict:
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    meta = doc.metadata or {}
    paragraphs: list[str] = []
    for page in doc:
        for block in page.get_text("blocks"):
            text = clean_text(block[4].replace("\n", " "))
            if len(text) >= 2:
                paragraphs.append(text)
    title = (meta.get("title") or "").strip() or Path(path).stem
    return {"title": title, "author": (meta.get("author") or "").strip(),
            "paragraphs": paragraphs, "pages": doc.page_count}


def _strip_html_to_paras(html: str) -> list[str]:
    html = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)</(p|h\d|li|div|tr)>", "\n\n", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", "", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
            .replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'"))
    return [clean_text(p) for p in text.split("\n\n") if len(clean_text(p)) >= 2]


def _resolve(base: str, href: str) -> str:
    parts = (base.split("/") if base else []) + href.split("/")
    out = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p and p != ".":
            out.append(p)
    return "/".join(out)


def extract_epub(path: str) -> dict:
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        container = ET.fromstring(z.read("META-INF/container.xml"))
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        opf_path = container.find(".//c:rootfile", ns).get("full-path")
        opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""
        opf = ET.fromstring(z.read(opf_path))
        ns_o = {"o": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
        title_el = opf.find(".//dc:title", ns_o)
        author_el = opf.find(".//dc:creator", ns_o)
        manifest = {}
        for item in opf.findall(".//o:manifest/o:item", ns_o):
            manifest[item.get("id")] = {
                "href": _resolve(opf_dir, item.get("href") or ""),
                "type": item.get("media-type") or "",
            }
        paragraphs: list[str] = []
        for ref in opf.findall(".//o:spine/o:itemref", ns_o):
            if ref.get("linear") == "no":
                continue
            item = manifest.get(ref.get("idref") or "")
            if not item or "html" not in item["type"] or item["href"] not in names:
                continue
            html = z.read(item["href"]).decode("utf-8", "ignore")
            paragraphs.extend(_strip_html_to_paras(html))
        return {"title": (title_el.text or Path(path).stem).strip() if title_el is not None else Path(path).stem,
                "author": (author_el.text or "").strip() if author_el is not None else "",
                "paragraphs": paragraphs, "pages": 0}


def extract_txt(path: str) -> dict:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1258", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    paragraphs = [clean_text(p.replace("\n", " ")) for p in re.split(r"\n\s*\n", text)]
    return {"title": Path(path).stem, "author": "",
            "paragraphs": [p for p in paragraphs if len(p) >= 2], "pages": 0}
