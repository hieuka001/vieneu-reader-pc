"""JavaScript chạy trong webview để bóc nội dung chương + bấm chương tiếp.
Viết thuần chuỗi để test được cấu trúc cơ bản."""

# Ưu tiên các vùng chứa quen thuộc của web truyện (gồm Sáng Tác Việt),
# không thấy thì chấm điểm theo tổng độ dài thẻ <p> của từng khối.
EXTRACT_JS = r"""
(() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const priority = ['#chapter-c', '.chapter-c', '#chapter-content', '.chapter-content',
                    '#content-chapter', '.reading-content', '#read-content',
                    '.page-content', '#chapter', '.chapter', 'article', 'main'];
  let root = null;
  for (const sel of priority) {
    const el = document.querySelector(sel);
    if (el && (el.innerText || '').length > 200) { root = el; break; }
  }
  if (!root) {
    let bestScore = 0;
    document.querySelectorAll('div, section').forEach(el => {
      let pLen = 0, pCount = 0;
      el.querySelectorAll(':scope p').forEach(p => { pLen += (p.innerText || '').length; pCount++; });
      if (pCount >= 3 && pLen > bestScore) { bestScore = pLen; root = el; }
    });
  }
  let paras = [];
  if (root) {
    root.querySelectorAll('p').forEach(p => {
      const t = clean(p.innerText);
      if (t.length >= 2) paras.push(t);
    });
    if (paras.length < 3) {
      paras = (root.innerText || '').split(/\n+/).map(clean).filter(s => s.length >= 25);
    }
  }
  const h = document.querySelector('h1');
  return JSON.stringify({ title: h ? clean(h.innerText) : clean(document.title), paras });
})()
"""

# Bấm nút/link chương tiếp ngay trong trang (kể cả web SPA như Sáng Tác Việt).
NEXT_JS = r"""
(() => {
  const re = /(chương\s*(sau|tiếp|mới)|next(\s*chapter)?|tiếp\s*theo)/i;
  const els = Array.from(document.querySelectorAll('a, button'));
  let el = els.find(e => { const t = (e.innerText || '').trim(); return t.length > 0 && t.length <= 30 && re.test(t); });
  if (!el) el = document.querySelector('a[rel="next"]');
  if (el) { el.scrollIntoView(); el.click(); return 'clicked'; }
  return 'notfound';
})()
"""
