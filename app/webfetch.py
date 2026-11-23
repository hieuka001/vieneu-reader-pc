"""Đọc truyện từ web: tải 1 trang chương -> {title, paragraphs, next_url}.

Cách bóc: ưu tiên vùng chứa quen thuộc của web truyện (id/class kiểu
chapter-c, chapter-content, entry-content...); nếu không thấy thì lấy
toàn bộ thẻ <p> dài trên trang. Link chương tiếp: rel="next" hoặc
anchor có chữ "chương sau / chương tiếp / next".
"""
import re
import urllib.parse
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
_CONTAINER_HINTS = ("chapter-c", "chapter-content", "chapter_content",
                    "entry-content", "post-content", "read-content",
                    "chapter-body", "main-content", "noidung", "content")
_NEXT_TEXT = re.compile(r"(chương\s*(sau|tiếp|mới)|next|tiếp\s*theo|›|»)", re.IGNORECASE)
_PREV_TEXT = re.compile(r"(chương\s*trước|prev|‹|«)", re.IGNORECASE)
_SKIP_PARA = re.compile(r"(danh sách chương|mục lục|đánh dấu|bình luận|comment|facebook| quảng cáo )", re.IGNORECASE)


def fetch_html(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or ""
    if not charset:
        m = re.search(rb'charset=["\']?([\w-]+)', raw[:4096])
        charset = m.group(1).decode() if m else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _text_of(fragment: str) -> str:
    t = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    t = re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
         .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
         .replace("&hellip;", "…"))
    return re.sub(r"\s+", " ", t).strip()


def _container_slice(html: str) -> str:
    for hint in _CONTAINER_HINTS:
        m = re.search(r'(?:id|class)\s*=\s*"[^"]*' + re.escape(hint) + r'[^"]*"', html, re.IGNORECASE)
        if m:
            return html[m.start(): m.start() + 400_000]
    return html


def _find_link(html: str, base_url: str, pattern: re.Pattern, rel: str) -> str:
    m = re.search(r'<a[^>]+rel\s*=\s*"[^"]*' + rel + r'[^"]*"[^>]+href\s*=\s*"([^"]+)"', html, re.IGNORECASE)
    if not m:
        m = re.search(r'<a[^>]+href\s*=\s*"([^"]+)"[^>]+rel\s*=\s*"[^"]*' + rel + r'[^"]*"', html, re.IGNORECASE)
    if m:
        return urllib.parse.urljoin(base_url, m.group(1))
    for am in re.finditer(r'<a[^>]+href\s*=\s*"([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
        label = _text_of(am.group(2))
        if label and len(label) <= 40 and pattern.search(label):
            return urllib.parse.urljoin(base_url, am.group(1))
    return ""


def parse_chapter_page(html: str, url: str) -> dict:
    title = ""
    m = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html)
    if m:
        title = _text_of(m.group(1))
    if not title:
        m = re.search(r"(?is)<title>(.*?)</title>", html)
        if m:
            title = _text_of(m.group(1)).split("|")[0].split("-")[0].strip()
    body = _container_slice(html)
    paras: list[str] = []
    seen: set[str] = set()
    for pm in re.finditer(r"(?is)<p[^>]*>(.*?)</p>", body):
        t = _text_of(pm.group(1))
        if len(t) < 25 or t in seen or _SKIP_PARA.search(t):
            continue
        seen.add(t)
        paras.append(t)
    if len(paras) < 3:  # trang dựng khác thường: nới lỏng, lấy cả đoạn ngắn
        for pm in re.finditer(r"(?is)<p[^>]*>(.*?)</p>", body):
            t = _text_of(pm.group(1))
            if len(t) >= 2 and t not in seen and not _SKIP_PARA.search(t):
                seen.add(t)
                paras.append(t)
    return {
        "title": title or "Chương web",
        "paragraphs": paras,
        "next_url": _find_link(html, url, _NEXT_TEXT, "next"),
        "prev_url": _find_link(html, url, _PREV_TEXT, "prev"),
    }


def fetch_chapter(url: str) -> dict:
    html = fetch_html(url)
    result = parse_chapter_page(html, url)
    if not result["paragraphs"]:
        raise ValueError("Không bóc được nội dung chương từ trang này "
                         "(trang có thể nạp bằng JavaScript hoặc chặn bot).")
    result["url"] = url
    return result
