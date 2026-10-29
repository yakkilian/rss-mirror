# Source: public Agefi articles API.
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import requests


API_URL = "https://api.agefi.com/v1/articles"
PAGES = 3
OUTPUT = Path("feeds/agefi.xml")

HEADERS = {
    "User-Agent": "Mozilla/5.0 ICTjournal-RSS-Mirror/1.0",
    "Accept": "application/json",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


session = requests.Session()
session.headers.update(HEADERS)

articles = []
seen = set()

for page in range(1, PAGES + 1):
    response = session.get(
        API_URL,
        params={"page": page},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    page_articles = payload.get("articles", [])
    if not isinstance(page_articles, list):
        raise ValueError("Réponse Agefi inattendue: articles n'est pas une liste")

    print(f"[INFO] Agefi page {page}: {len(page_articles)} articles")

    for article in page_articles:
        actions = article.get("actions") or {}
        browser_urls = actions.get("browserUrls") or {}
        url = browser_urls.get("main")
        title = (article.get("title") or "").strip()

        if not url or not title or url in seen:
            continue

        seen.add(url)
        articles.append(article)

if not articles:
    raise ValueError("Aucun article Agefi récupéré")

articles.sort(
    key=lambda a: (
        parse_iso(((a.get("dates") or {}).get("publishedAt")))
        or datetime.min.replace(tzinfo=timezone.utc)
    ),
    reverse=True,
)

rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")

ET.SubElement(channel, "title").text = "L'Agefi - Actualités"
ET.SubElement(channel, "link").text = "https://agefi.com/actualites"
ET.SubElement(channel, "description").text = (
    "Actualités de L'Agefi, générées depuis l'API publique du site "
    "pour la veille ICTjournal."
)
ET.SubElement(channel, "language").text = "fr-CH"
ET.SubElement(channel, "lastBuildDate").text = format_datetime(
    datetime.now(timezone.utc)
)

for article in articles:
    actions = article.get("actions") or {}
    browser_urls = actions.get("browserUrls") or {}
    api_urls = actions.get("apiUrls") or {}

    url = browser_urls.get("main")
    category_url = browser_urls.get("category") or ""
    api_url = api_urls.get("main") or url
    title = (article.get("title") or "").strip()
    subtitle = (article.get("subtitle") or "").strip()

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url
    ET.SubElement(item, "guid", isPermaLink="false").text = api_url

    if subtitle:
        ET.SubElement(item, "description").text = subtitle

    published = parse_iso((article.get("dates") or {}).get("publishedAt"))
    if published:
        ET.SubElement(item, "pubDate").text = format_datetime(published)

    if category_url:
        category = category_url.rstrip("/").split("/")[-1]
        if category:
            ET.SubElement(item, "category").text = category

    for tag in (article.get("tags") or [])[:8]:
        name = (tag.get("name") or "").strip() if isinstance(tag, dict) else ""
        if name:
            ET.SubElement(item, "category").text = name

OUTPUT.parent.mkdir(exist_ok=True)

tree = ET.ElementTree(rss)
ET.indent(tree, space="  ")
tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True,
)

print(f"[OK] agefi: {len(articles)} articles -> {OUTPUT}")
