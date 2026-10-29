import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

url = "https://home.cern/tag/news/"
headers = {
    "User-Agent": "Mozilla/5.0 ICTjournal-RSS-Mirror/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,en-US;q=0.9,fr;q=0.7",
}

r = requests.get(url, headers=headers, timeout=30)
r.raise_for_status()
soup = BeautifulSoup(r.text, "html.parser")

print("STATUS:", r.status_code, "LEN:", len(r.content))

for idx, tm in enumerate(soup.find_all("time")[:12], 1):
    print("\n--- ITEM", idx, "---")
    print("TIME:", tm.get("datetime"), "|", " ".join(tm.stripped_strings))
    node = tm
    for level in range(1, 7):
        node = node.parent
        if node is None:
            break
        links = []
        for a in node.find_all("a", href=True):
            text = " ".join(a.stripped_strings).strip()
            href = urljoin(r.url, a["href"])
            if (text, href) not in links:
                links.append((text, href))
        if links:
            print("LEVEL", level, "TAG", node.name, "CLASS", node.get("class"))
            for text, href in links[:10]:
                print(" A:", repr(text[:220]), "=>", href)
            raw = re.sub(r"\s+", " ", " ".join(node.stripped_strings))
            print(" TEXT:", raw[:900])
            break
