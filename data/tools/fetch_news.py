"""Fetches a news article URL and saves it as markdown (title, URL, date, fetch time, paragraph text) under data/companies/<slug>/.

Usage: python3 data/tools/fetch_news.py <slug> <out_name.md> <url> [fallback_date]
Downloaded content is untrusted data: only text of <p> and <h1> elements is kept, nothing is executed.
"""
import re
import subprocess
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


class Extract(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.date = ""
        self.paras: list[str] = []
        self._tag = ""
        self._buf = ""
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "nav", "footer", "noscript"):
            self._skip += 1
        if tag == "meta" and a.get("property") in ("article:published_time", "og:updated_time") and not self.date:
            self.date = (a.get("content") or "")[:10]
        if tag in ("p", "h1", "li") and not self._skip:
            self._tag, self._buf = tag, ""

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "noscript") and self._skip:
            self._skip -= 1
        if tag == self._tag:
            text = re.sub(r"\s+", " ", self._buf).strip()
            if tag == "h1" and not self.title:
                self.title = text
            elif len(text) > 60:
                self.paras.append(text)
            self._tag = ""

    def handle_data(self, data):
        if self._tag:
            self._buf += data


def main() -> None:
    slug, name, url = sys.argv[1:4]
    fallback = sys.argv[4] if len(sys.argv) > 4 else "unknown"
    html = subprocess.run(["curl", "-sL", "-m", "40", "-A", UA, url], capture_output=True, check=True).stdout.decode("utf-8", "replace")
    p = Extract()
    p.feed(html)
    if len(p.paras) < 3:
        sys.exit(f"too little text extracted from {url}")
    seen: list[str] = []
    for para in p.paras:
        if para not in seen:
            seen.append(para)
    body = "\n\n".join(seen[:40])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = Path("data/companies") / slug / name
    out.write_text(f"# {p.title or name}\n\n- URL: {url}\n- Published: {p.date or fallback}\n- Fetched: {now}\n\n{body}\n")
    print(out, len(body))


main()
