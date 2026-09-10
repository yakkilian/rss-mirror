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
    "apple": "https://www.apple.com/newsroom/rss-feed.rss",
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

# Création d'un RSS à partir de Fortinet Threat Research
try:
    fortinet_threat_url = "https://www.fortinet.com/blog/threat-research"
    r = requests.get(fortinet_threat_url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        url = urljoin(fortinet_threat_url, href)
        title = " ".join(link.stripped_strings)

        if "/blog/threat-research/" not in url:
            continue

        if url.rstrip("/") == fortinet_threat_url.rstrip("/"):
            continue

        if not title or len(title) < 10:
            continue

        if url in seen:
            continue

        seen.add(url)
        items.append((title, url))

        if len(items) >= 30:
            break

    if not items:
        raise ValueError("Aucun article Fortinet Threat Research trouvé")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "Fortinet Threat Research"
    ET.SubElement(channel, "link").text = fortinet_threat_url
    ET.SubElement(channel, "description").text = "FortiGuard Labs Threat Research"

    for title, url in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(
        OUTPUT_DIR / "fortinet-threat.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] fortinet-threat: {len(items)} articles")
    successes += 1

except Exception as e:
    print(f"[ERREUR] fortinet-threat: {e}")


    # Création d'un RSS à partir du Quotidien Jurassien - Jura
try:
    lqj_url = "https://www.lqj.ch/region/jura/"

    r = requests.get(lqj_url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        url = urljoin(lqj_url, href)

        if "/articles/" not in url:
            continue

        if url in seen:
            continue

        title = " ".join(link.stripped_strings).strip()

        # Enlève la date et le résumé éventuellement inclus dans la carte
        if " Publié " in title:
            title = title.split(" Publié ")[0].strip()

        if not title or len(title) < 10:
            continue

        seen.add(url)
        items.append((title, url))

        if len(items) >= 40:
            break

    if not items:
        raise ValueError("Aucun article LQJ Jura trouvé")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "Le Quotidien Jurassien – Jura"
    ET.SubElement(channel, "link").text = lqj_url
    ET.SubElement(channel, "description").text = "Actualités jurassiennes du Quotidien Jurassien"

    for title, url in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(
        OUTPUT_DIR / "lqj-jura.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] lqj-jura: {len(items)} articles")
    successes += 1

except Exception as e:
    print(f"[ERREUR] lqj-jura: {e}")
    # Création d'un RSS à partir des actualités de l'Etat du Valais
try:
    valais_url = "https://www.vs.ch/web/communication"

    r = requests.get(valais_url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        url = urljoin(valais_url, href)
        title = " ".join(link.stripped_strings).strip()

        if "/web/communication/e/com-et-media/" not in url:
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
        raise ValueError("Aucune actualité Valais trouvée")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "Etat du Valais – Communication"
    ET.SubElement(channel, "link").text = valais_url
    ET.SubElement(channel, "description").text = "Actualités et communiqués de l'Etat du Valais"

    for title, url in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(
        OUTPUT_DIR / "valais.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] valais: {len(items)} actualités")
    successes += 1

except Exception as e:
    print(f"[ERREUR] valais: {e}")
    
if successes == 0:
    raise SystemExit("Aucun flux n'a pu être récupéré")
