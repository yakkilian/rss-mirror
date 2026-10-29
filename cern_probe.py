import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

URLS = [
    "https://home.cern/tag/news/",
    "https://home.cern/news/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 ICTjournal-RSS-Mirror/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,en-US;q=0.9,fr;q=0.7",
}

for url in URLS:
    print("\n" + "="*80)
    print("URL:", url)
    r = requests.get(url, headers=HEADERS, timeout=30)
    print("STATUS:", r.status_code)
    print("FINAL:", r.url)
    print("TYPE:", r.headers.get("content-type"))
    print("LEN:", len(r.content))
    print("HEAD:", re.sub(r"\s+"," ",r.text[:1200]))

    soup = BeautifulSoup(r.text, "html.parser")
    seen = set()
    hits = []
    for a in soup.find_all("a", href=True):
        href = urljoin(r.url, a["href"])
        title = " ".join(a.stripped_strings).strip()
        if href in seen:
            continue
        seen.add(href)
        if "/news/" in href and len(title) >= 8:
            hits.append((title, href))
    print("NEWS LINKS:", len(hits))
    for t,h in hits[:40]:
        print("LINK:", t[:180], "=>", h)

    times = soup.find_all("time")
    print("TIME ELEMENTS:", len(times))
    for tm in times[:20]:
        print("TIME:", tm.get("datetime"), "|", " ".join(tm.stripped_strings))
