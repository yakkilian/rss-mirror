import json
import os
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
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

# Pour le test, on ne prend que les articles des dernières 48 heures.
LOOKBACK_HOURS = 48

# Nombre maximal d'entrées demandées à chaque flux FreshRSS.
MAX_ITEMS = 100


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
    """
    Ajoute les paramètres FreshRSS.
    On conserve aussi un filtrage de 48 h côté FreshRSS,
    même si le script vérifie lui-même la date ensuite.
    """
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


def is_recent(entry):
    """
    Vérifie directement dans le script que l'article date
    des dernières LOOKBACK_HOURS heures.
    """

    date_value = (
        entry.get("published")
        or entry.get("updated")
        or ""
    )

    # Si aucune date n'est disponible, on conserve l'article
    # par prudence plutôt que de risquer de manquer une news.
    if not date_value:
        return True

    try:
        dt = parsedate_to_datetime(date_value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(hours=LOOKBACK_HOURS)
        )

        return dt >= cutoff

    except Exception:
        # Date impossible à interpréter:
        # on conserve l'article par prudence.
        return True


def rss_fallback(entry):
    """
    Texte fourni par le RSS si le texte intégral
    de la page ne peut pas être extrait.
    """
    chunks = []

    if entry.get("summary"):
        chunks.append(entry.summary)

    for content in entry.get("content", []):
        if content.get("value"):
            chunks.append(content["value"])

    text = " ".join(chunks)

    return re.sub(r"<[^>]+>", " ", text)


def fetch_full_text(url, fallback=""):
    """
    Télécharge l'article et extrait son contenu principal.
    Si cela échoue, utilise le contenu présent dans le RSS.
    """
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
        print(
            f"[WARN] Texte intégral inaccessible: "
            f"{url}: {e}"
        )

    return fallback.strip(), "rss"


def find_matches(text, keywords):
    """
    Recherche les mots-clés sans tenir compte
    des majuscules/minuscules.

    IA et TIC doivent apparaître comme mots complets.
    'cyber' peut en revanche détecter cybersécurité,
    cyberattaque, cybercriminel, etc.
    """
    matches = []

    for keyword in keywords:

        if keyword in ("IA", "TIC"):

            pattern = rf"\b{re.escape(keyword)}\b"

            if re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
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

    print(
        f"[INFO] {len(parsed.entries)} "
        f"articles reçus de FreshRSS"
    )

    recent_count = 0

    for entry in parsed.entries:

        # IMPORTANT:
        # on élimine ici les vieux articles AVANT
        # de télécharger leurs pages web.
        if not is_recent(entry):
            continue

        recent_count += 1

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

        # Aucun filtre lexical pour ces deux catégories.
        if group in ("ICTj news", "ICT best"):
            keep = True

        # Sources suisses:
        # recherche des mots-clés IT.
        elif group == "Suisse":

            matches = find_matches(
                searchable,
                SWISS_IT_KEYWORDS,
            )

            keep = bool(matches)

        # Sources ICT:
        # recherche d'un lien géographique avec la Suisse.
        elif group == "ICT":

            matches = find_matches(
                searchable,
                ICT_SWISS_KEYWORDS,
            )

            keep = bool(matches)

        if not keep:
            continue

        # Déduplication par URL.
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
                "excerpt": full_text[:2000],
            }

        else:

            if group not in selected[url]["groups"]:
                selected[url]["groups"].append(group)

            for match in matches:
                if (
                    match
                    not in selected[url]["matched_keywords"]
                ):
                    selected[url][
                        "matched_keywords"
                    ].append(match)

    print(
        f"[INFO] {recent_count} articles "
        f"datent des dernières {LOOKBACK_HOURS} h"
    )


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

    keywords = ", ".join(
        article["matched_keywords"]
    )

    print(
        f"\n[{groups}] "
        f"{article['title']}"
    )

    if keywords:
        print(
            f"  mots-clés: {keywords}"
        )

    print(
        f"  {article['url']}"
    )
