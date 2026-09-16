import calendar
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests
from trafilatura import extract


# ============================================================
# CONFIGURATION
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/152 Safari/537.36"
    )
}

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Fenêtre temporelle de travail
LOOKBACK_HOURS = 48

# FreshRSS nous a correctement renvoyé 100 articles.
# On garde donc 100 par page et on utilise offset pour paginer.
PAGE_SIZE = 100

# Sécurité: maximum 10 pages = 1000 articles par groupe.
MAX_PAGES = 10

# Téléchargements simultanés des pages web
MAX_WORKERS = 12


FEEDS = {
    "Suisse": os.environ["FRESHRSS_AUTO_SUISSE"],
    "ICTj news": os.environ["FRESHRSS_AUTO_ICTJ_NEWS"],
    "ICT best": os.environ["FRESHRSS_AUTO_ICT_BEST"],
    "ICT": os.environ["FRESHRSS_AUTO_ICT"],
}


# ============================================================
# MOTS-CLÉS
# ============================================================

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


# ============================================================
# FRESHRSS
# ============================================================

def freshrss_url(url, offset=None):
    """
    Construit l'URL FreshRSS.

    Première page: aucun paramètre offset.
    Pages suivantes: offset=100, 200, etc.
    """

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))

    query["f"] = "rss"
    query["nb"] = str(PAGE_SIZE)
    query["hours"] = str(LOOKBACK_HOURS)
    query["order"] = "DESC"

    # IMPORTANT:
    # pas de offset=0 sur la première page
    if offset is not None:
        query["offset"] = str(offset)
    else:
        query.pop("offset", None)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def fetch_freshrss_entries(group, feed_url):
    """
    Récupère les articles FreshRSS par pages de 100.

    La première page est appelée sans offset,
    exactement comme dans notre version qui fonctionnait.
    """

    entries = []
    seen = set()

    for page_number in range(MAX_PAGES):

        if page_number == 0:
            # Première page: PAS de offset
            url = freshrss_url(
                feed_url,
                offset=None,
            )
        else:
            # Pages suivantes: 100, 200, 300...
            url = freshrss_url(
                feed_url,
                offset=page_number * PAGE_SIZE,
            )

        # On utilise directement feedparser,
        # comme dans la première version qui fonctionnait.
        parsed = feedparser.parse(url)

        if parsed.bozo:
            print(
                f"[WARN] Flux {group}, page "
                f"{page_number + 1}: "
                f"{parsed.bozo_exception}"
            )

        page_entries = parsed.entries

        print(
            f"[INFO] {group}: page "
            f"{page_number + 1} -> "
            f"{len(page_entries)} articles"
        )

        if not page_entries:
            break

        added_this_page = 0

        for entry in page_entries:

            key = (
                entry.get("link")
                or entry.get("id")
                or (
                    entry.get("title", "")
                    + entry.get("published", "")
                )
            )

            if not key:
                continue

            if key in seen:
                continue

            seen.add(key)
            entries.append(entry)
            added_this_page += 1

        # Moins de 100 = dernière page.
        if len(page_entries) < PAGE_SIZE:
            break

        # Si FreshRSS ignore offset et renvoie
        # exactement les mêmes articles, on arrête.
        if added_this_page == 0:
            print(
                f"[WARN] {group}: pagination arrêtée, "
                "la page ne contient aucun nouvel article"
            )
            break

    return entries

# ============================================================
# DATES
# ============================================================

def entry_datetime(entry):
    """
    Essaie plusieurs formats de date proposés par feedparser.
    """

    for key in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):

        value = entry.get(key)

        if value:
            try:
                timestamp = calendar.timegm(value)

                return datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                )

            except Exception:
                pass

    date_value = (
        entry.get("published")
        or entry.get("updated")
        or ""
    )

    if date_value:
        try:
            dt = parsedate_to_datetime(date_value)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt.astimezone(timezone.utc)

        except Exception:
            pass

    return None


def is_recent(entry):
    """
    Double contrôle local des 48 dernières heures.

    FreshRSS applique déjà hours=48, mais on ne dépend
    pas uniquement de lui.
    """

    dt = entry_datetime(entry)

    # Sans date exploitable, on conserve par prudence.
    if dt is None:
        return True

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=LOOKBACK_HOURS)
    )

    return dt >= cutoff


# ============================================================
# CONTENU RSS
# ============================================================

def rss_fallback(entry):
    """
    Récupère le chapô / contenu fourni par FreshRSS.
    """

    chunks = []

    if entry.get("summary"):
        chunks.append(entry["summary"])

    for content in entry.get("content", []):
        if content.get("value"):
            chunks.append(content["value"])

    text = " ".join(chunks)

    text = html.unescape(text)

    # Suppression simple des balises HTML
    text = re.sub(r"<[^>]+>", " ", text)

    # Nettoyage des espaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# RÉCUPÉRATION DU TEXTE INTÉGRAL
# ============================================================

def fetch_full_text(url):
    """
    Télécharge la page de l'article et tente d'en extraire
    le contenu éditorial principal avec Trafilatura.

    Retour:
    (texte, succès, erreur)
    """

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
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
            return text.strip(), True, ""

        return "", False, "extraction insuffisante"

    except requests.HTTPError as e:

        status = (
            e.response.status_code
            if e.response is not None
            else "?"
        )

        return "", False, f"HTTP {status}"

    except requests.Timeout:

        return "", False, "timeout"

    except Exception as e:

        return "", False, str(e)[:200]


# ============================================================
# FILTRAGE PAR MOTS-CLÉS
# ============================================================

def find_matches(text, keywords):
    """
    Recherche insensible à la casse.

    IA et TIC doivent apparaître comme mots entiers.
    'cyber' détecte volontairement cybersécurité,
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


# ============================================================
# AJOUT D'UN ARTICLE RETENU
# ============================================================

def add_selected(
    selected,
    entry,
    group,
    matches,
    text,
    text_source,
    selection_reason,
):

    url = entry.get("link", "").strip()
    title = entry.get("title", "").strip()

    if not url or not title:
        return

    if url not in selected:

        selected[url] = {
            "title": title,
            "url": url,
            "groups": [group],
            "published": (
                entry.get("published")
                or entry.get("updated")
                or ""
            ),
            "matched_keywords": list(matches),
            "text_source": text_source,
            "selection_reason": selection_reason,

            # Pour l'instant, on conserve jusqu'à 2000 caractères.
            # Cela inclut notamment les chapôs FreshRSS.
            "excerpt": text[:2000],
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


# ============================================================
# TRAITEMENT DES 4 GROUPES
# ============================================================

selected = {}

unresolved = []

# Pages qui nécessitent un téléchargement intégral.
# Pour l'instant seulement Suisse + ICT.
to_fetch = {}

stats = {}


for group, feed_url in FEEDS.items():

    print("\n==============================")
    print(f"=== {group} ===")
    print("==============================")

    all_entries = fetch_freshrss_entries(
        group,
        feed_url,
    )

    received = len(all_entries)

    recent_entries = [
        entry
        for entry in all_entries
        if is_recent(entry)
    ]

    print(
        f"[INFO] {received} articles uniques "
        "reçus de FreshRSS"
    )

    print(
        f"[INFO] {len(recent_entries)} articles "
        f"datent des dernières {LOOKBACK_HOURS} h"
    )

    stats[group] = {
        "received": received,
        "recent": len(recent_entries),
        "selected": 0,
        "unresolved": 0,
    }

    for entry in recent_entries:

        url = entry.get("link", "").strip()
        title = entry.get("title", "").strip()

        if not url or not title:
            continue

        rss_text = rss_fallback(entry)

        # ----------------------------------------------------
        # ICTj news / ICT best
        #
        # Aucun filtre lexical:
        # tous les articles récents deviennent candidats.
        #
        # On conserve déjà leur chapô / extrait RSS.
        # Le texte intégral sera récupéré plus tard,
        # avant la sélection éditoriale par IA.
        # ----------------------------------------------------

        if group in ("ICTj news", "ICT best"):

            add_selected(
                selected=selected,
                entry=entry,
                group=group,
                matches=[],
                text=rss_text,
                text_source="rss",
                selection_reason="all_from_group",
            )

            stats[group]["selected"] += 1

            continue

        # ----------------------------------------------------
        # Suisse / ICT
        #
        # Ici le texte intégral est utile dès maintenant,
        # puisque nous devons y chercher des mots-clés.
        # ----------------------------------------------------

        if url not in to_fetch:
            to_fetch[url] = []

        to_fetch[url].append(
            {
                "group": group,
                "entry": entry,
                "rss_text": rss_text,
            }
        )


print("\n==============================")
print(
    f"[INFO] {len(to_fetch)} pages web uniques "
    "à analyser en texte intégral"
)
print("==============================")


# ============================================================
# TÉLÉCHARGEMENT PARALLÈLE
# ============================================================

fetch_results = {}


with ThreadPoolExecutor(
    max_workers=MAX_WORKERS
) as executor:

    futures = {
        executor.submit(
            fetch_full_text,
            url,
        ): url
        for url in to_fetch
    }

    for future in as_completed(futures):

        url = futures[future]

        try:

            fetch_results[url] = future.result()

        except Exception as e:

            fetch_results[url] = (
                "",
                False,
                str(e)[:200],
            )


# ============================================================
# FILTRAGE SUISSE / ICT
# ============================================================

for url, records in to_fetch.items():

    full_text, success, error = fetch_results.get(
        url,
        ("", False, "aucun résultat"),
    )

    for record in records:

        group = record["group"]
        entry = record["entry"]
        rss_text = record["rss_text"]

        title = entry.get("title", "").strip()

        if group == "Suisse":
            keywords = SWISS_IT_KEYWORDS
        else:
            keywords = ICT_SWISS_KEYWORDS

        # ----------------------------------------------------
        # Cas 1: texte intégral disponible
        # ----------------------------------------------------

        if success:

            searchable = (
                f"{title}\n{full_text}"
            )

            matches = find_matches(
                searchable,
                keywords,
            )

            if matches:

                add_selected(
                    selected=selected,
                    entry=entry,
                    group=group,
                    matches=matches,
                    text=full_text,
                    text_source="full",
                    selection_reason="keyword_fulltext",
                )

                stats[group]["selected"] += 1

            continue

        # ----------------------------------------------------
        # Cas 2: page inaccessible
        #
        # On essaie titre + chapô FreshRSS.
        # ----------------------------------------------------

        searchable = (
            f"{title}\n{rss_text}"
        )

        matches = find_matches(
            searchable,
            keywords,
        )

        if matches:

            add_selected(
                selected=selected,
                entry=entry,
                group=group,
                matches=matches,
                text=rss_text,
                text_source="rss",
                selection_reason="keyword_rss_fallback",
            )

            stats[group]["selected"] += 1

        else:

            # ------------------------------------------------
            # IMPORTANT:
            #
            # L'article n'est PAS jeté.
            # Il passe dans unresolved.json afin qu'une
            # autre méthode puisse l'examiner ensuite.
            # ------------------------------------------------

            unresolved.append(
                {
                    "title": title,
                    "url": url,
                    "group": group,
                    "published": (
                        entry.get("published")
                        or entry.get("updated")
                        or ""
                    ),
                    "fetch_error": error,
                    "rss_excerpt": rss_text[:2000],
                }
            )

            stats[group]["unresolved"] += 1


# ============================================================
# FICHIERS DE SORTIE
# ============================================================

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


with open(
    OUTPUT_DIR / "unresolved.json",
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        unresolved,
        f,
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# RÉSUMÉ DU RUN
# ============================================================

print("\n==============================")
print("RÉSUMÉ PAR GROUPE")
print("==============================")


for group, s in stats.items():

    print(
        f"{group}: "
        f"{s['received']} reçus | "
        f"{s['recent']} récents | "
        f"{s['selected']} retenus | "
        f"{s['unresolved']} à vérifier"
    )


print("\n==============================")
print(f"ARTICLES RETENUS: {len(results)}")
print(
    f"ARTICLES À VÉRIFIER: "
    f"{len(unresolved)}"
)
print("==============================")


# Affichage des candidats pour contrôle manuel
for article in results:

    groups = ", ".join(
        article["groups"]
    )

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
        f"  source texte: "
        f"{article['text_source']}"
    )

    print(
        f"  {article['url']}"
    )
