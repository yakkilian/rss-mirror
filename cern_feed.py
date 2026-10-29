# Source: CERN public news tag pages.
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://home.cern/tag/news/"
PAGES = 3
OUTPUT = Path("feeds/cern.xml")

HEADERS = {
    "User-Agent": "Mozilla/5.0 ICTjournal-RSS-Mirror/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,en-US;q=0.9,fr;q=0.7",
}


def page_url(page):
    return BASE_URL if page == 1 else urljoin(BASE_URL, f"page/{page}/")


def clean_text(value):
    return " ".join((value or "").split())


session = requests.Session()
session.headers.update(HEADERS)

items = []
seen = set()

for page in range(1, PAGES + 1):
    url = page_url(page)
    response = session.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    times = soup.find_all("time")
    print(f"[INFO] CERN page {page}: {len(times)} dated cards")

    for tm in times:
        dt_raw = tm.get("datetime")
        if not dt_raw:
            continue

        card = tm.parent.parent
        if card is None:
            continue

        heading = card.find(["h2", "h3", "h4", "h5"])
        title = clean_text(heading.get_text(" ", strip=True)) if heading else ""

        link = None
        for a in card.find_all("a", href=True):
            href = urljoin(response.url, a["href"])
            text = clean_text(a.get_text(" ", strip=True)).lower()
            if text.startswith("explore") and href.startswith("https://home.cern/"):
                link = href
                break

        if not link:
            for a in card.find_all("a", href=True):
                href = urljoin(response.url, a["href"])
                if href.startswith("https://home.cern/") and href.rstrip("/") != BASE_URL.rstrip("/"):
                    link = href
                    break

        if not title or not link or link in seen:
            continue

        seen.add(link)

        description = ""
        paragraphs = []
        for p in card.find_all("p"):
            text = clean_text(p.get_text(" ", strip=True))
            if len(text) >= 40 and text != title:
                paragraphs.append(text)

        if paragraphs:
            description = max(paragraphs, key=len)

        try:
            published = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
        except Exception:
            published = None

        items.append({
            "title": title,
            "link": link,
            "description": description,
            "published": published,
        })

if not items:
    raise ValueError("Aucune actualité CERN récupérée")

items.sort(
    key=lambda item: item["published"] or datetime.min.replace(tzinfo=timezone.utc),
    reverse=True,
)

rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")

ET.SubElement(channel, "title").text = "CERN - News"
ET.SubElement(channel, "link").text = BASE_URL
ET.SubElement(channel, "description").text = (
    "Latest CERN news mirrored for FreshRSS and ICTjournal monitoring."
)
ET.SubElement(channel, "language").text = "en"
ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))

for article in items:
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = article["title"]
    ET.SubElement(item, "link").text = article["link"]
    ET.SubElement(item, "guid", isPermaLink="true").text = article["link"]

    if article["description"]:
        ET.SubElement(item, "description").text = article["description"]

    if article["published"]:
        ET.SubElement(item, "pubDate").text = format_datetime(article["published"])

OUTPUT.parent.mkdir(exist_ok=True)

tree = ET.ElementTree(rss)
ET.indent(tree, space="  ")
tree.write(OUTPUT, encoding="utf-8", xml_declaration=True)

print(f"[OK] cern: {len(items)} articles -> {OUTPUT}")
