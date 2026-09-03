from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

FEEDS = {
    "paloalto": "https://investors.paloaltonetworks.com/rss/news-releases.xml",
    "nutanix": "https://ir.nutanix.com/rss/news-releases.xml",
    "fortinet": "https://investor.fortinet.com/rss/news-releases.xml",
    "dell": "https://investors.delltechnologies.com/rss/news-releases.xml",
}

OUTPUT_DIR = Path("feeds")
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 ICTjournal-RSS-Mirror/1.0",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html, */*;q=0.8",
}

successes = 0

# Copie des vrais flux RSS
for name, url in FEEDS.items():
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()

        content = r.content
        check = content.lstrip().lower()[:500]

        if not any(marker in check for marker in (b"<rss", b"<feed", b"<rdf:rdf", b"<?xml")):
            raise ValueError("La réponse ne ressemble pas à un flux RSS/Atom")

        (OUTPUT_DIR / f"{name}.xml").write_bytes(content)
        print(f"[OK] {name}: {len(content)} octets")
        successes += 1

    except Exception as e:
        print(f"[ERREUR] {name}: {e}")

# Création d'un RSS à partir de la newsroom ABB
try:
    abb_url = "https://new.abb.com/ch"
    r = requests.get(abb_url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        title = " ".join(link.stripped_strings)

        if not title or len(title) < 10:
            continue

        if "/global/en/news/" not in href and "/news/detail/" not in href:
            continue

        url = urljoin(abb_url, href)

        if url in seen:
            continue

        seen.add(url)
        items.append((title, url))

        if len(items) >= 30:
            break

    if not items:
        raise ValueError("Aucun communiqué ABB trouvé dans la page")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "ABB Group press releases"
    ET.SubElement(channel, "link").text = abb_url
    ET.SubElement(channel, "description").text = "ABB Group press releases mirrored for FreshRSS"

    for title, url in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(
        OUTPUT_DIR / "abb.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] abb: {len(items)} communiqués")
    successes += 1

except Exception as e:
    print(f"[ERREUR] abb: {e}")
# Création d'un RSS à partir des communiqués de presse de La Poste
try:
    post_url = "https://www.post.ch/fr/notre-profil/medias/communiques-de-presse"
    r = requests.get(post_url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        url = urljoin(post_url, href)
        title = " ".join(link.stripped_strings)

        if (
            "/fr/notre-profil/medias/communiques-de-presse/" not in url
            and "/fr/notre-profil/service-de-presse/communiques-de-presse/" not in url
        ):
            continue

        if not title or len(title) < 10:
            continue

        if url in seen:
            continue

        seen.add(url)
        items.append((title, url))

        if len(items) >= 50:
            break

    if not items:
        raise ValueError("Aucun communiqué de La Poste trouvé dans la page")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "La Poste Suisse - Communiqués de presse"
    ET.SubElement(channel, "link").text = post_url
    ET.SubElement(channel, "description").text = "Communiqués de presse de La Poste Suisse"

    for title, url in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(
        OUTPUT_DIR / "post.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] post: {len(items)} communiqués")
    successes += 1

except Exception as e:
    print(f"[ERREUR] post: {e}")
    
if successes == 0:
    raise SystemExit("Aucun flux n'a pu être récupéré")
