import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/155.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
}

URLS = [
    "https://agefi.com/robots.txt",
    "https://agefi.com/sitemap.xml",
    "https://agefi.com/sitemap_index.xml",
    "https://agefi.com/sitemap-index.xml",
    "https://agefi.com/actualites",
    "https://api.agefi.com/",
]

session = requests.Session()
session.headers.update(HEADERS)

for url in URLS:
    print("\n" + "=" * 80)
    print("URL:", url)

    try:
        r = session.get(url, timeout=30, allow_redirects=True)
        print("STATUS:", r.status_code)
        print("FINAL:", r.url)
        print("CONTENT-TYPE:", r.headers.get("content-type"))
        print("LENGTH:", len(r.content))

        text = r.text
        compact = re.sub(r"\s+", " ", text[:1200])
        print("HEAD:", compact)

        if "xml" in (r.headers.get("content-type") or "").lower() or "<urlset" in text[:5000] or "<sitemapindex" in text[:5000]:
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", text, flags=re.I | re.S)
            article_locs = [x for x in locs if "/actualites/" in x]
            print("XML LOCS:", len(locs))
            print("XML ARTICLE LOCS:", len(article_locs))
            for item in article_locs[:20]:
                print("  ARTICLE:", item)

        if "text/html" in (r.headers.get("content-type") or "").lower() or "<html" in text[:1000].lower():
            soup = BeautifulSoup(text, "html.parser")
            hrefs = []
            seen = set()

            for a in soup.find_all("a", href=True):
                absolute = urljoin(r.url, a["href"])
                if "/actualites/" in absolute and absolute not in seen:
                    seen.add(absolute)
                    hrefs.append(absolute)

            print("HTML ARTICLE HREFS:", len(hrefs))
            for item in hrefs[:20]:
                print("  HREF:", item)

            scripts = [urljoin(r.url, s["src"]) for s in soup.find_all("script", src=True)]
            print("SCRIPT SRCS:", len(scripts))
            for src in scripts[:20]:
                print("  SCRIPT:", src)

            if "api.agefi.com" in text:
                print("FOUND api.agefi.com IN HTML")
                for m in re.finditer(r".{0,180}api\.agefi\.com.{0,260}", text, flags=re.I | re.S):
                    print("  API CONTEXT:", re.sub(r"\s+", " ", m.group(0))[:500])

            raw_articles = sorted(set(re.findall(r"https?://[^\"'<>\\s]+/actualites/[^\"'<>\\s]+", text)))
            print("RAW ARTICLE URLS:", len(raw_articles))
            for item in raw_articles[:20]:
                print("  RAW:", item)

    except Exception as e:
        print("ERROR:", repr(e))
