import json
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
    "Accept": "text/html,application/xhtml+xml,application/json,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
}

SITE_URLS = [
    "https://agefi.com/robots.txt",
    "https://agefi.com/sitemap.xml",
    "https://agefi.com/sitemap_index.xml",
    "https://agefi.com/sitemap-index.xml",
    "https://agefi.com/actualites",
]

API_URLS = [
    "https://api.agefi.com/",
    "https://api.agefi.com/v1",
    "https://api.agefi.com/v1/",
    "https://api.agefi.com/docs",
    "https://api.agefi.com/v1/docs",
    "https://api.agefi.com/openapi.json",
    "https://api.agefi.com/v1/openapi.json",
    "https://api.agefi.com/swagger.json",
    "https://api.agefi.com/v1/articles",
    "https://api.agefi.com/v1/posts",
    "https://api.agefi.com/v1/news",
    "https://api.agefi.com/v1/actualites",
    "https://api.agefi.com/v1/contents",
    "https://api.agefi.com/v1/content",
    "https://api.agefi.com/v1/search",
]

session = requests.Session()
session.headers.update(HEADERS)


def report(url, full=False):
    print("\n" + "=" * 80)
    print("URL:", url)

    try:
        r = session.get(url, timeout=30, allow_redirects=True)
        print("STATUS:", r.status_code)
        print("FINAL:", r.url)
        print("CONTENT-TYPE:", r.headers.get("content-type"))
        print("LENGTH:", len(r.content))

        text = r.text
        if full:
            print("BODY:")
            print(text[:12000])
        else:
            compact = re.sub(r"\s+", " ", text[:1800])
            print("HEAD:", compact)

        content_type = (r.headers.get("content-type") or "").lower()

        if "json" in content_type:
            try:
                payload = r.json()
                print("JSON TYPE:", type(payload).__name__)
                if isinstance(payload, dict):
                    print("JSON KEYS:", sorted(payload.keys())[:100])
                    if isinstance(payload.get("articles"), list):
                        print("ARTICLE COUNT:", len(payload["articles"]))
                    if "pagination" in payload:
                        print("PAGINATION:", json.dumps(payload["pagination"], ensure_ascii=False))
                elif isinstance(payload, list):
                    print("JSON ITEMS:", len(payload))
                    if payload:
                        print("FIRST ITEM:", json.dumps(payload[0], ensure_ascii=False)[:2000])
            except Exception as e:
                print("JSON PARSE ERROR:", repr(e))

        if "xml" in content_type or "<urlset" in text[:5000] or "<sitemapindex" in text[:5000]:
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", text, flags=re.I | re.S)
            article_locs = [x for x in locs if "/actualites/" in x]
            print("XML LOCS:", len(locs))
            print("XML ARTICLE LOCS:", len(article_locs))
            for item in article_locs[:20]:
                print("  ARTICLE:", item)

        if "text/html" in content_type or "<html" in text[:1000].lower():
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

    except Exception as e:
        print("ERROR:", repr(e))


for url in SITE_URLS:
    report(url, full=url.endswith("/robots.txt"))

print("\n" + "#" * 80)
print("# API PROBE")
print("#" * 80)

for url in API_URLS:
    report(url)
