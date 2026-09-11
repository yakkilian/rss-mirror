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
    "oracle": "https://www.oracle.com/corporate/press/rss/rss-pr.xml",
    "broadcom": "https://investors.broadcom.com/rss/news-releases.xml",
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

# Création d'un RSS à partir du blog SANS
try:
    sans_url = "https://www.sans.org/blog"

    r = requests.get(sans_url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        url = urljoin(sans_url, href)
        title = " ".join(link.stripped_strings).strip()

        if not url.startswith("https://www.sans.org/blog/"):
            continue

        if url.rstrip("/") == sans_url.rstrip("/"):
            continue

        if not title or len(title) < 15:
            continue

        if url in seen:
            continue

        seen.add(url)
        items.append((title, url))

        if len(items) >= 40:
            break

    if not items:
        raise ValueError("Aucun article SANS trouvé")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "SANS Blog"
    ET.SubElement(channel, "link").text = sans_url
    ET.SubElement(channel, "description").text = "Derniers articles du blog SANS"

    for title, url in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(
        OUTPUT_DIR / "sans.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] sans: {len(items)} articles")
    successes += 1

except Exception as e:
    print(f"[ERREUR] sans: {e}")
    # Création d'un RSS à partir des communiqués Omdia
try:
    omdia_url = "https://omdia.tech.informa.com/pr"

    r = requests.get(omdia_url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        url = urljoin(omdia_url, href)
        title = " ".join(link.stripped_strings).strip()

        if not url.startswith("https://omdia.tech.informa.com/pr/"):
            continue

        if url.rstrip("/") == omdia_url.rstrip("/"):
            continue

        if not title or len(title) < 15:
            continue

        if url in seen:
            continue

        seen.add(url)
        items.append((title, url))

        if len(items) >= 40:
            break

    if not items:
        raise ValueError("Aucun communiqué Omdia trouvé")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "Omdia – Press Releases"
    ET.SubElement(channel, "link").text = omdia_url
    ET.SubElement(channel, "description").text = "Derniers communiqués Omdia"

    for title, url in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(
        OUTPUT_DIR / "omdia.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] omdia: {len(items)} communiqués")
    successes += 1

except Exception as e:
    print(f"[ERREUR] omdia: {e}")
    # Création d'un RSS à partir de la press room Deloitte Suisse
try:
    import gzip
    import re
    from urllib.parse import urlsplit, urlunsplit

    deloitte_url = "https://www.deloitte.com/ch/fr/about/press-room.html"

    # Deloitte utilise un index global de sitemaps.
    sitemap_roots = [
        "https://www.deloitte.com/sitemap_index.xml",
        "https://www.deloitte.com/ch/fr/sitemap_index.xml",
        "https://www.deloitte.com/ch/fr/sitemap.xml",
    ]

    PRESS_PREFIX = "/ch/fr/about/press-room/"

    candidates = {}
    visited_sitemaps = set()

    def clean_url(url):
        """Supprime query string et fragment."""
        p = urlsplit(url)
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))

    def is_press_release(url):
        p = urlsplit(url)

        return (
            p.netloc.lower() in ("www.deloitte.com", "deloitte.com")
            and p.path.startswith(PRESS_PREFIX)
            and p.path.endswith(".html")
            and p.path != "/ch/fr/about/press-room.html"
        )

    def get_xml(url):
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()

        data = r.content

        # Certains sitemaps peuvent être gzipés.
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)

        return ET.fromstring(data)

    def local_name(tag):
        return tag.split("}")[-1]

    def crawl_sitemap(url, depth=0):
        if url in visited_sitemaps:
            return

        if depth > 3:
            return

        if len(visited_sitemaps) >= 150:
            return

        visited_sitemaps.add(url)

        try:
            root = get_xml(url)
        except Exception as e:
            print(f"[WARN] deloitte-ch sitemap ignoré: {url}: {e}")
            return

        root_type = local_name(root.tag)

        # Sitemap index -> contient d'autres sitemaps
        if root_type == "sitemapindex":

            child_sitemaps = []

            for sitemap in root:
                if local_name(sitemap.tag) != "sitemap":
                    continue

                loc = None

                for child in sitemap:
                    if local_name(child.tag) == "loc":
                        loc = (child.text or "").strip()
                        break

                if loc:
                    child_sitemaps.append(loc)

            # L'index global Deloitte contient les variantes régionales.
            # On privilégie celles dont le nom semble correspondre à CH.
            if depth == 0:
                swiss = [
                    u for u in child_sitemaps
                    if re.search(
                        r"(^|[/_.-])ch([/_.-]|$)",
                        urlsplit(u).path.lower()
                    )
                ]

                if swiss:
                    child_sitemaps = swiss

            for child_url in child_sitemaps:
                crawl_sitemap(child_url, depth + 1)

        # Sitemap normal -> contient les pages
        elif root_type == "urlset":

            for entry in root:
                if local_name(entry.tag) != "url":
                    continue

                loc = None
                lastmod = ""

                for child in entry:
                    name = local_name(child.tag)

                    if name == "loc":
                        loc = (child.text or "").strip()

                    elif name == "lastmod":
                        lastmod = (child.text or "").strip()

                if not loc:
                    continue

                loc = clean_url(loc)

                if not is_press_release(loc):
                    continue

                candidates[loc] = lastmod

    # 1. Tentative via les sitemaps Deloitte
    for sitemap_url in sitemap_roots:
        crawl_sitemap(sitemap_url)

        if candidates:
            break

    # 2. Secours: recherche Bing en RSS
    if not candidates:
        print("[WARN] deloitte-ch: aucun résultat via sitemap, tentative Bing RSS")

        bing = requests.get(
            "https://www.bing.com/search",
            params={
                "q": 'site:www.deloitte.com/ch/fr/about/press-room/ "Deloitte Suisse"',
                "format": "rss",
            },
            headers=HEADERS,
            timeout=60,
        )
        bing.raise_for_status()

        bing_root = ET.fromstring(bing.content)

        for item in bing_root.findall(".//item"):
            link = item.findtext("link")

            if not link:
                continue

            link = clean_url(link.strip())

            if is_press_release(link):
                candidates[link] = ""

    if not candidates:
        raise ValueError("Aucun communiqué Deloitte Suisse trouvé")

    # Les URLs les plus récemment modifiées d'abord
    urls = sorted(
        candidates,
        key=lambda u: candidates[u],
        reverse=True
    )[:40]

    items = []

    # Récupération du véritable titre de chaque communiqué
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")

            h1 = soup.find("h1")

            if not h1:
                continue

            title = " ".join(h1.stripped_strings).strip()

            if not title:
                continue

            description = ""

            meta_desc = soup.find(
                "meta",
                attrs={"name": "description"}
            )

            if meta_desc and meta_desc.get("content"):
                description = meta_desc["content"].strip()

            items.append({
                "title": title,
                "url": url,
                "description": description,
            })

        except Exception as article_error:
            print(
                f"[WARN] deloitte-ch article ignoré: "
                f"{url}: {article_error}"
            )

    if not items:
        raise ValueError(
            "Communiqués Deloitte trouvés mais impossible de lire leurs pages"
        )

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(
        channel,
        "title"
    ).text = "Deloitte Suisse – Press Room"

    ET.SubElement(
        channel,
        "link"
    ).text = deloitte_url

    ET.SubElement(
        channel,
        "description"
    ).text = "Derniers communiqués Deloitte Suisse"

    for entry in items:
        item = ET.SubElement(channel, "item")

        ET.SubElement(
            item,
            "title"
        ).text = entry["title"]

        ET.SubElement(
            item,
            "link"
        ).text = entry["url"]

        ET.SubElement(
            item,
            "guid",
            isPermaLink="true"
        ).text = entry["url"]

        if entry["description"]:
            ET.SubElement(
                item,
                "description"
            ).text = entry["description"]

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")

    tree.write(
        OUTPUT_DIR / "deloitte-ch.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] deloitte-ch: {len(items)} communiqués")
    successes += 1

except Exception as e:
    print(f"[ERREUR] deloitte-ch: {e}")
    # Création d'un RSS à partir des communiqués Forrester
try:
    forrester_url = "https://www.forrester.com/forrester-news/press-release/"
    press_prefix = "https://www.forrester.com/press-newsroom/"

    items = []
    seen = set()

    # Les deux premières pages suffisent pour récupérer les communiqués récents
    archive_pages = [
        forrester_url,
        "https://www.forrester.com/forrester-news/press-release/page/2/",
    ]

    for archive_url in archive_pages:
        r = requests.get(archive_url, headers=HEADERS, timeout=60)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        for link in soup.find_all("a", href=True):
            url = urljoin(archive_url, link["href"])

            # Seuls les véritables communiqués
            if not url.startswith(press_prefix):
                continue

            if url.rstrip("/") == press_prefix.rstrip("/"):
                continue

            if url in seen:
                continue

            title = " ".join(link.stripped_strings).strip()

            # Les liens "Read More" pointent aussi vers le communiqué:
            # on ne garde que le lien portant le vrai titre.
            if not title or title.lower() in ("read more", "en savoir plus"):
                continue

            if len(title) < 15:
                continue

            seen.add(url)

            description = ""

            # Récupération du chapô/meta description
            try:
                article_r = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=30
                )
                article_r.raise_for_status()

                article_soup = BeautifulSoup(
                    article_r.text,
                    "html.parser"
                )

                # Le H1 est la référence pour le titre
                h1 = article_soup.find("h1")
                if h1:
                    article_title = " ".join(
                        h1.stripped_strings
                    ).strip()

                    if article_title:
                        title = article_title

                meta_desc = article_soup.find(
                    "meta",
                    attrs={"name": "description"}
                )

                if meta_desc and meta_desc.get("content"):
                    description = meta_desc["content"].strip()

            except Exception as article_error:
                print(
                    f"[WARN] forrester article: "
                    f"{url}: {article_error}"
                )

            items.append({
                "title": title,
                "url": url,
                "description": description,
            })

            if len(items) >= 40:
                break

        if len(items) >= 40:
            break

    if not items:
        raise ValueError("Aucun communiqué Forrester trouvé")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(
        channel,
        "title"
    ).text = "Forrester – Press Releases"

    ET.SubElement(
        channel,
        "link"
    ).text = forrester_url

    ET.SubElement(
        channel,
        "description"
    ).text = "Derniers communiqués de presse Forrester"

    for entry in items:
        item = ET.SubElement(channel, "item")

        ET.SubElement(
            item,
            "title"
        ).text = entry["title"]

        ET.SubElement(
            item,
            "link"
        ).text = entry["url"]

        ET.SubElement(
            item,
            "guid",
            isPermaLink="true"
        ).text = entry["url"]

        if entry["description"]:
            ET.SubElement(
                item,
                "description"
            ).text = entry["description"]

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")

    tree.write(
        OUTPUT_DIR / "forrester.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] forrester: {len(items)} communiqués")
    successes += 1

except Exception as e:
    print(f"[ERREUR] forrester: {e}")
    # Création d'un RSS à partir des communiqués KPMG Suisse
try:
    kpmg_url = "https://kpmg.com/ch/en/media.html"

    items = []
    seen = set()

    r = requests.get(kpmg_url, headers=HEADERS, timeout=60)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    for link in soup.find_all("a", href=True):
        url = urljoin(kpmg_url, link["href"])

        if "/ch/en/media/press-releases/" not in url:
            continue

        # Nettoyage éventuel des paramètres / fragments
        url = url.split("#")[0].split("?")[0]

        if url in seen:
            continue

        seen.add(url)

        try:
            article_r = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )
            article_r.raise_for_status()

            article_soup = BeautifulSoup(
                article_r.text,
                "html.parser"
            )

            final_url = url
            final_soup = article_soup

            # Cherche la version française officielle déclarée
            # dans les balises hreflang de l'article.
            french_url = None

            for alt in article_soup.find_all(
                "link",
                attrs={"hreflang": True, "href": True}
            ):
                hreflang = (
                    alt.get("hreflang") or ""
                ).lower()

                rel = alt.get("rel", [])

                if isinstance(rel, str):
                    rel = [rel]

                if (
                    "alternate" in rel
                    and hreflang.startswith("fr")
                ):
                    candidate = urljoin(
                        url,
                        alt["href"]
                    )

                    if "/ch/fr/" in candidate:
                        french_url = candidate
                        break

            # Si KPMG propose une version française,
            # on l'utilise à la place de l'anglaise.
            if french_url:
                try:
                    fr_r = requests.get(
                        french_url,
                        headers=HEADERS,
                        timeout=30
                    )
                    fr_r.raise_for_status()

                    fr_soup = BeautifulSoup(
                        fr_r.text,
                        "html.parser"
                    )

                    fr_h1 = fr_soup.find("h1")

                    if (
                        fr_h1
                        and "/ch/fr/" in fr_r.url
                    ):
                        final_url = fr_r.url.split("#")[0].split("?")[0]
                        final_soup = fr_soup

                except Exception as fr_error:
                    print(
                        f"[WARN] kpmg-ch version FR indisponible: "
                        f"{french_url}: {fr_error}"
                    )

            h1 = final_soup.find("h1")

            if not h1:
                continue

            title = " ".join(
                h1.stripped_strings
            ).strip()

            if not title:
                continue

            description = ""

            meta_desc = final_soup.find(
                "meta",
                attrs={"name": "description"}
            )

            if meta_desc and meta_desc.get("content"):
                description = meta_desc["content"].strip()

            items.append({
                "title": title,
                "url": final_url,
                "description": description,
            })

            if len(items) >= 40:
                break

        except Exception as article_error:
            print(
                f"[WARN] kpmg-ch article ignoré: "
                f"{url}: {article_error}"
            )

    if not items:
        raise ValueError(
            "Aucun communiqué KPMG Suisse trouvé"
        )

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(
        channel,
        "title"
    ).text = "KPMG Suisse – Communiqués de presse"

    ET.SubElement(
        channel,
        "link"
    ).text = "https://kpmg.com/ch/fr/media.html"

    ET.SubElement(
        channel,
        "description"
    ).text = "Derniers communiqués de presse de KPMG Suisse"

    for entry in items:
        item = ET.SubElement(channel, "item")

        ET.SubElement(
            item,
            "title"
        ).text = entry["title"]

        ET.SubElement(
            item,
            "link"
        ).text = entry["url"]

        ET.SubElement(
            item,
            "guid",
            isPermaLink="true"
        ).text = entry["url"]

        if entry["description"]:
            ET.SubElement(
                item,
                "description"
            ).text = entry["description"]

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")

    tree.write(
        OUTPUT_DIR / "kpmg-ch.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] kpmg-ch: {len(items)} communiqués")
    successes += 1

except Exception as e:
    print(f"[ERREUR] kpmg-ch: {e}")
    # Création d'un RSS à partir des communiqués Nielsen
try:
    nielsen_url = "https://www.nielsen.com/news-center/type/press-release/"

    items = []
    seen = set()

    archive_pages = [
        nielsen_url,
        "https://www.nielsen.com/news-center/type/press-release/page/2/",
    ]

    for archive_url in archive_pages:
        r = requests.get(
            archive_url,
            headers=HEADERS,
            timeout=60
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        for link in soup.find_all("a", href=True):
            url = urljoin(archive_url, link["href"])
            url = url.split("#")[0].split("?")[0]

            # Les véritables articles du News Center
            if "/news-center/" not in url:
                continue

            # Exclusion des pages d'archive
            if "/type/" in url or "/page/" in url:
                continue

            if url.rstrip("/") == "https://www.nielsen.com/news-center":
                continue

            if url in seen:
                continue

            seen.add(url)

            try:
                article_r = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=30
                )
                article_r.raise_for_status()

                article_soup = BeautifulSoup(
                    article_r.text,
                    "html.parser"
                )

                final_url = url
                final_soup = article_soup

                # Recherche d'une version française officielle
                french_url = None

                for alt in article_soup.find_all(
                    "link",
                    attrs={"hreflang": True, "href": True}
                ):
                    hreflang = (
                        alt.get("hreflang") or ""
                    ).lower()

                    if hreflang.startswith("fr"):
                        candidate = urljoin(
                            url,
                            alt["href"]
                        )

                        if "/fr/news-center/" in candidate:
                            french_url = candidate
                            break

                # Si Nielsen propose une traduction française,
                # on l'utilise.
                if french_url:
                    try:
                        fr_r = requests.get(
                            french_url,
                            headers=HEADERS,
                            timeout=30
                        )
                        fr_r.raise_for_status()

                        fr_soup = BeautifulSoup(
                            fr_r.text,
                            "html.parser"
                        )

                        if fr_soup.find("h1"):
                            final_url = (
                                fr_r.url
                                .split("#")[0]
                                .split("?")[0]
                            )
                            final_soup = fr_soup

                    except Exception as fr_error:
                        print(
                            f"[WARN] nielsen version FR indisponible: "
                            f"{french_url}: {fr_error}"
                        )

                h1 = final_soup.find("h1")

                if not h1:
                    continue

                title = " ".join(
                    h1.stripped_strings
                ).strip()

                if not title:
                    continue

                description = ""

                meta_desc = final_soup.find(
                    "meta",
                    attrs={"name": "description"}
                )

                if meta_desc and meta_desc.get("content"):
                    description = meta_desc["content"].strip()

                items.append({
                    "title": title,
                    "url": final_url,
                    "description": description,
                })

                if len(items) >= 40:
                    break

            except Exception as article_error:
                print(
                    f"[WARN] nielsen article ignoré: "
                    f"{url}: {article_error}"
                )

        if len(items) >= 40:
            break

    if not items:
        raise ValueError(
            "Aucun communiqué Nielsen trouvé"
        )

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(
        channel,
        "title"
    ).text = "Nielsen – Communiqués de presse"

    ET.SubElement(
        channel,
        "link"
    ).text = nielsen_url

    ET.SubElement(
        channel,
        "description"
    ).text = "Derniers communiqués de presse Nielsen"

    for entry in items:
        item = ET.SubElement(channel, "item")

        ET.SubElement(
            item,
            "title"
        ).text = entry["title"]

        ET.SubElement(
            item,
            "link"
        ).text = entry["url"]

        ET.SubElement(
            item,
            "guid",
            isPermaLink="true"
        ).text = entry["url"]

        if entry["description"]:
            ET.SubElement(
                item,
                "description"
            ).text = entry["description"]

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")

    tree.write(
        OUTPUT_DIR / "nielsen.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"[OK] nielsen: {len(items)} communiqués")
    successes += 1

except Exception as e:
    print(f"[ERREUR] nielsen: {e}")
    # Création d'un RSS à partir des communiqués PwC Suisse
try:
    pwc_url = "https://www.pwc.ch/fr/centre-de-presse.html"
    press_prefix = "https://www.pwc.ch/fr/centre-de-presse/"

    candidates = []
    seen = set()

    def add_pwc_url(url):
        url = url.split("#")[0].split("?")[0]

        if not url.startswith(press_prefix):
            return

        if not url.endswith(".html"):
            return

        if url in seen:
            return

        seen.add(url)
        candidates.append(url)

    # 1. Lecture directe de la page médias PwC Suisse
    r = requests.get(
        pwc_url,
        headers=HEADERS,
        timeout=60
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    for link in soup.find_all("a", href=True):
        url = urljoin(pwc_url, link["href"])
        add_pwc_url(url)

    # 2. Secours si les communiqués sont chargés dynamiquement
    if not candidates:
        print(
            "[WARN] pwc-ch: aucun lien dans le HTML, "
            "tentative via Bing RSS"
        )

        bing = requests.get(
            "https://www.bing.com/search",
            params={
                "q": (
                    "site:www.pwc.ch/fr/centre-de-presse/ "
                    "\"PwC Suisse\""
                ),
                "format": "rss",
            },
            headers=HEADERS,
            timeout=60,
        )
        bing.raise_for_status()

        bing_root = ET.fromstring(bing.content)

        for item in bing_root.findall(".//item"):
            link = item.findtext("link")

            if link:
                add_pwc_url(link.strip())

    if not candidates:
        raise ValueError(
            "Aucun communiqué PwC Suisse trouvé"
        )

    items = []

    # Lecture des pages individuelles
    for url in candidates[:40]:
        try:
            article_r = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )
            article_r.raise_for_status()

            article_soup = BeautifulSoup(
                article_r.text,
                "html.parser"
            )

            h1 = article_soup.find("h1")

            if not h1:
                continue

            title = " ".join(
                h1.stripped_strings
            ).strip()

            if not title:
                continue

            # Vérification supplémentaire:
            # les pages de communiqué PwC indiquent généralement
            # "Press Release"
            page_text = article_soup.get_text(
                " ",
                strip=True
            )

            if "Press Release" not in page_text:
                print(
                    f"[WARN] pwc-ch page ignorée "
                    f"(pas identifiée comme Press Release): {url}"
                )
                continue

            description = ""

            meta_desc = article_soup.find(
                "meta",
                attrs={"name": "description"}
            )

            if meta_desc and meta_desc.get("content"):
                description = (
                    meta_desc["content"].strip()
                )

            items.append({
                "title": title,
                "url": url,
                "description": description,
            })

        except Exception as article_error:
            print(
                f"[WARN] pwc-ch article ignoré: "
                f"{url}: {article_error}"
            )

    if not items:
        raise ValueError(
            "Communiqués PwC trouvés mais "
            "aucune page exploitable"
        )

    rss = ET.Element(
        "rss",
        version="2.0"
    )

    channel = ET.SubElement(
        rss,
        "channel"
    )

    ET.SubElement(
        channel,
        "title"
    ).text = "PwC Suisse – Communiqués de presse"

    ET.SubElement(
        channel,
        "link"
    ).text = pwc_url

    ET.SubElement(
        channel,
        "description"
    ).text = (
        "Derniers communiqués de presse de PwC Suisse"
    )

    for entry in items:
        item = ET.SubElement(
            channel,
            "item"
        )

        ET.SubElement(
            item,
            "title"
        ).text = entry["title"]

        ET.SubElement(
            item,
            "link"
        ).text = entry["url"]

        ET.SubElement(
            item,
            "guid",
            isPermaLink="true"
        ).text = entry["url"]

        if entry["description"]:
            ET.SubElement(
                item,
                "description"
            ).text = entry["description"]

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")

    tree.write(
        OUTPUT_DIR / "pwc-ch.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print(
        f"[OK] pwc-ch: "
        f"{len(items)} communiqués"
    )

    successes += 1

except Exception as e:
    print(f"[ERREUR] pwc-ch: {e}")
if successes == 0:
    raise SystemExit("Aucun flux n'a pu être récupéré")
