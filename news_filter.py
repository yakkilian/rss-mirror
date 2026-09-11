import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests
from trafilatura import extract


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/152 Safari/537.36"
    )
}

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

LOOKBACK_HOURS = 48
MAX_ITEMS = 200


FEEDS = {
    "Suisse": os.environ["FRESHRSS_AUTO_SUISSE"],
    "ICTj news": os.environ["FRESHRSS_AUTO_ICTJ_NEWS"],
    "ICT best": os.environ["FRESHRSS_AUTO_ICT_BEST"],
    "ICT": os.environ["FRESHRSS_AUTO_ICT"],
}


SWISS_IT_KEYWORDS = [
    "numérique",
    "informatique",
    "digital",
    "intelligence artificielle",
    "cyberattaque",
    "cyber",
    "quantique",
    "technologie",
    "technologies",
    "digitale",
    "TIC",
    "IA",
    "web",
    "internet",
    "blockchain",
    "bug",
    "logiciel",
    "application",
    "électronique",
    "médiamaticien",
]


ICT_SWISS_KEYWORDS = [
    "switzerland",
    "swiss",
    "Zurich",
    "Geneva",
    "Lausanne",
]


def freshrss_url(url):
    """Ajoute les paramètres pour récupérer suffisamment d'articles récents."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))

    query["f"] = "rss"
    query["nb"] = str(MAX_ITEMS)
    query["hours"] = str(LOOKBACK_HOURS)
    query["order"] = "DESC"

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def rss_fallback(entry):
    """Texte fourni par le RSS si l'article complet est inaccessible."""
    chunks = []

    if entry.get("summary"):
        chunks.append(entry.summary)

    for content in entry.get("content", []):
        if content.get("value"):
            chunks.append(content["value"])

    text = " ".join(chunks)

    # Suppression grossière des balises HTML
    return re.sub(r"<[^>]+>", " ", text)


def fetch_full_text(url, fallback=""):
    """Télécharge la page et extrait son contenu éditorial principal."""
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )
        r.raise_for_status()

        text = extract(
            r.text,
            url=r.url,
            include_comments=False,
            include_tables=False,
        )

        if text and len(text.strip()) >= 200:
            return text.strip(), "full"

    except Exception as e:
        print(f"[WARN] Texte intégral inaccessible: {url}: {e}")

    return fallback.strip(), "rss"


def find_matches(text, keywords):
    """
    Recherche insensible à la casse.
    IA et TIC sont limités à des mots complets.
    Les autres mots fonctionnent comme des sous-chaînes:
    'cyber' détectera donc aussi 'cybersécurité'.
    """
    matches = []

    for keyword in keywords:
        if keyword in ("IA", "TIC"):
            pattern = rf"\b{re.escape(keyword)}\b"

            if re.search(pattern, text, flags=re.IGNORECASE):
                matches.append(keyword)

        elif keyword.lower() in text.lower():
            matches.append(keyword)

    return matches


selected = {}


for group, feed_url in FEEDS.items():

    print(f"\n=== {group} ===")

    parsed = feedparser.parse(
        freshrss_url(feed_url)
    )

    if parsed.bozo:
        print(
            f"[WARN] Flux {group}: "
            f"{parsed.bozo_exception}"
        )

    print(f"[INFO] {len(parsed.entries)} articles reçus")

    for entry in parsed.entries:

        url = entry.get("link", "").strip()
        title = entry.get("title", "").strip()

        if not url or not title:
            continue

        fallback = rss_fallback(entry)

        full_text, extraction = fetch_full_text(
            url,
            fallback=fallback,
        )

        searchable = f"{title}\n{full_text}"

        keep = False
        matches = []

        # Ces deux catégories sont intégralement conservées
        if group in ("ICTj news", "ICT best"):
            keep = True

        # Filtre IT sur les sources suisses
        elif group == "Suisse":
            matches = find_matches(
                searchable,
                SWISS_IT_KEYWORDS,
            )
            keep = bool(matches)

        # Filtre géographique sur les sources ICT
        elif group == "ICT":
            matches = find_matches(
                searchable,
                ICT_SWISS_KEYWORDS,
            )
            keep = bool(matches)

        if not keep:
            continue

        # Déduplication si le même article apparaît dans plusieurs groupes
        if url not in selected:

            selected[url] = {
                "title": title,
                "url": url,
                "groups": [group],
                "published": entry.get(
                    "published",
                    entry.get("updated", ""),
                ),
                "matched_keywords": matches,
                "text_source": extraction,

                # Suffisant pour vérifier les résultats;
                # on ne stocke pas des articles entiers dans GitHub.
                "excerpt": full_text[:2000],
            }

        else:
            if group not in selected[url]["groups"]:
                selected[url]["groups"].append(group)

            for match in matches:
                if match not in selected[url]["matched_keywords"]:
                    selected[url]["matched_keywords"].append(match)


results = list(selected.values())


with open(
    OUTPUT_DIR / "candidates.json",
    "w",
    encoding="utf-8",
) as f:
    json.dump(
        results,
        f,
        ensure_ascii=False,
        indent=2,
    )


print("\n==============================")
print(f"ARTICLES RETENUS: {len(results)}")
print("==============================")

for article in results:
    groups = ", ".join(article["groups"])
    keywords = ", ".join(article["matched_keywords"])

    print(f"\n[{groups}] {article['title']}")

    if keywords:
        print(f"  mots-clés: {keywords}")

    print(f"  {article['url']}")
