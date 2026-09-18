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

LOOKBACK_HOURS = 48

PAGE_SIZE = 100
MAX_PAGES = 10

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
# URLS / DÉDOUBLONNAGE
# ============================================================

def canonical_key(url):
    """
    Retire quelques paramètres de tracking afin que deux URL
    identiques ne deviennent pas deux candidats différents.
    """

    try:
        parts = urlsplit(url)

        clean_query = []

        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True,
        ):
            low = key.lower()

            if low.startswith("utm_"):
                continue

            if low in {
                "feedref",
                "oc",
            }:
                continue

            clean_query.append((key, value))

        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                parts.path.rstrip("/"),
                urlencode(clean_query),
                "",
            )
        )

    except Exception:
        return url


def businesswire_language(url):
    """
    Détecte la langue dans une URL Business Wire, par exemple:
    /en/
    /fr/
    /de/
    /it/
    /zh-CN/
    """

    try:
        parts = urlsplit(url)

        if "businesswire.com" not in parts.netloc.lower():
            return None

        match = re.search(
            r"/news/home/\d+/([A-Za-z]{2}(?:-[A-Za-z]{2})?)(?:/|$)",
            parts.path,
        )

        if match:
            return match.group(1).lower()

    except Exception:
        pass

    return None


def skip_unverified_businesswire_translation(url):
    """
    Cette règle ne s'applique QU'AUX articles dont le texte
    intégral est inaccessible ET dont aucun mot-clé n'a été
    trouvé dans le titre/chapô.

    Dans ce cas de précaution, on ne transmet à l'IA que les
    versions françaises et anglaises de Business Wire.

    Un article Business Wire qui a réellement passé le filtre
    lexical n'est jamais supprimé ici.
    """

    lang = businesswire_language(url)

    if lang is None:
        return False

    return lang not in {"fr", "en"}


# ============================================================
# FRESHRSS
# ============================================================

def freshrss_url(url, offset=None):
    """
    Pas de paramètre hours:
    il vide le flux sur cette instance FreshRSS.

    Le contrôle des 48 h est effectué en Python.
    """

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))

    query["f"] = "rss"
    query["nb"] = str(PAGE_SIZE)
    query["order"] = "DESC"

    query.pop("hours", None)

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
    Récupère les pages FreshRSS de 100 articles.

    Arrêt dès qu'une page entière ne contient plus
    aucun article des dernières 48 h.
    """

    entries = []
    seen = set()

    for page_number in range(MAX_PAGES):

        if page_number == 0:
            url = freshrss_url(
                feed_url,
                offset=None,
            )
        else:
            url = freshrss_url(
                feed_url,
                offset=page_number * PAGE_SIZE,
            )

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
        recent_this_page = 0

        for entry in page_entries:

            if is_recent(entry):
                recent_this_page += 1

            raw_url = (
                entry.get("link")
                or entry.get("id")
                or ""
            )

            key = (
                canonical_key(raw_url)
                if raw_url
                else (
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

        print(
            f"[INFO] {group}: "
            f"{recent_this_page} articles récents "
            "sur cette page"
        )

        if len(page_entries) < PAGE_SIZE:
            break

        if recent_this_page == 0:
            print(
                f"[INFO] {group}: arrêt pagination, "
                f"plus aucun article des dernières "
                f"{LOOKBACK_HOURS} h"
            )
            break

        if added_this_page == 0:
            print(
                f"[WARN] {group}: pagination arrêtée, "
                "aucun nouvel article sur cette page"
            )
            break

    return entries


# ============================================================
# DATES
# ============================================================

def entry_datetime(entry):

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

    dt = entry_datetime(entry)

    # Sans date exploitable, conservation par prudence.
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

    chunks = []

    if entry.get("summary"):
        chunks.append(entry["summary"])

    for content in entry.get("content", []):
        if content.get("value"):
            chunks.append(content["value"])

    text = " ".join(chunks)

    text = html.unescape(text)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# TEXTE INTÉGRAL
# ============================================================

def fetch_full_text(url):

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
# MOTS-CLÉS
# ============================================================

def find_matches(text, keywords):

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
# AJOUT D'UN CANDIDAT
# ============================================================

def add_selected(
    selected,
    entry,
    group,
    matches,
    text,
    text_source,
    selection_reason,
    needs_ai_review=False,
    fetch_error="",
):

    url = entry.get("link", "").strip()
    title = entry.get("title", "").strip()

    if not url or not title:
        return

    key = canonical_key(url)

    if key not in selected:

        selected[key] = {
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
            "needs_ai_review": needs_ai_review,
            "fetch_error": fetch_error,

            # Titre + chapô / extrait seront donc disponibles
            # pour la future étape IA.
            "excerpt": text[:3000],
        }

    else:

        if group not in selected[key]["groups"]:
            selected[key]["groups"].append(group)

        for match in matches:

            if (
                match
                not in selected[key]["matched_keywords"]
            ):
                selected[key][
                    "matched_keywords"
                ].append(match)


# ============================================================
# TRAITEMENT
# ============================================================

selected = {}

# Ce fichier reste un diagnostic technique.
# Ses articles peuvent désormais AUSSI être présents
# dans candidates.json.
unresolved = []

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
        "keyword_match": 0,
        "precaution": 0,
        "businesswire_skipped": 0,
    }

    for entry in recent_entries:

        url = entry.get("link", "").strip()
        title = entry.get("title", "").strip()

        if not url or not title:
            continue

        rss_text = rss_fallback(entry)

        # ----------------------------------------------------
        # ICTj news / ICT best:
        # tout passe à l'étape IA.
        # Le chapô RSS est conservé.
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
                needs_ai_review=False,
            )

            stats[group]["selected"] += 1

            continue

        # ----------------------------------------------------
        # Suisse / ICT:
        # téléchargement du texte intégral pour
        # appliquer correctement le filtre lexical.
        # ----------------------------------------------------

        key = canonical_key(url)

        if key not in to_fetch:
            to_fetch[key] = {
                "url": url,
                "records": [],
            }

        to_fetch[key]["records"].append(
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
            data["url"],
        ): key
        for key, data in to_fetch.items()
    }

    for future in as_completed(futures):

        key = futures[future]

        try:

            fetch_results[key] = future.result()

        except Exception as e:

            fetch_results[key] = (
                "",
                False,
                str(e)[:200],
            )


# ============================================================
# FILTRAGE SUISSE / ICT
# ============================================================

for key, data in to_fetch.items():

    url = data["url"]

    full_text, success, error = fetch_results.get(
        key,
        ("", False, "aucun résultat"),
    )

    for record in data["records"]:

        group = record["group"]
        entry = record["entry"]
        rss_text = record["rss_text"]

        title = entry.get(
            "title",
            "",
        ).strip()

        if group == "Suisse":
            keywords = SWISS_IT_KEYWORDS
        else:
            keywords = ICT_SWISS_KEYWORDS

        # ----------------------------------------------------
        # TEXTE INTÉGRAL DISPONIBLE
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
                    needs_ai_review=False,
                )

                stats[group]["selected"] += 1
                stats[group]["keyword_match"] += 1

            continue

        # ----------------------------------------------------
        # TEXTE INTÉGRAL INACCESSIBLE
        #
        # On essaie le titre + chapô FreshRSS.
        # ----------------------------------------------------

        searchable = (
            f"{title}\n{rss_text}"
        )

        matches = find_matches(
            searchable,
            keywords,
        )

        if matches:

            # Le mot-clé est déjà confirmé par le RSS.
            add_selected(
                selected=selected,
                entry=entry,
                group=group,
                matches=matches,
                text=rss_text,
                text_source="rss",
                selection_reason="keyword_rss_fallback",
                needs_ai_review=False,
                fetch_error=error,
            )

            stats[group]["selected"] += 1
            stats[group]["keyword_match"] += 1

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
                    "rss_excerpt": rss_text[:3000],
                    "candidate_action": (
                        "included_keyword_match"
                    ),
                }
            )

            continue

        # ----------------------------------------------------
        # PAS DE TEXTE INTÉGRAL + PAS DE MOT-CLÉ VISIBLE
        #
        # Au lieu de jeter l'article, on le transmet à l'IA
        # avec son chapô RSS comme candidat de précaution.
        # ----------------------------------------------------

        diagnostic = {
            "title": title,
            "url": url,
            "group": group,
            "published": (
                entry.get("published")
                or entry.get("updated")
                or ""
            ),
            "fetch_error": error,
            "rss_excerpt": rss_text[:3000],
        }

        # ----------------------------------------------------
        # Business Wire:
        #
        # parmi ces candidats NON CONFIRMÉS uniquement,
        # on évite de transmettre toutes les traductions.
        #
        # FR + EN conservés.
        # Les autres langues restent dans unresolved.json
        # pour audit, mais ne sont pas envoyées à l'IA.
        # ----------------------------------------------------

        if skip_unverified_businesswire_translation(
            url
        ):

            diagnostic[
                "candidate_action"
            ] = (
                "excluded_non_fr_en_businesswire"
            )

            unresolved.append(
                diagnostic
            )

            stats[group][
                "businesswire_skipped"
            ] += 1

            continue

        # Candidat de précaution transmis à l'IA.
        diagnostic[
            "candidate_action"
        ] = "included_for_ai_review"

        unresolved.append(
            diagnostic
        )

        add_selected(
            selected=selected,
            entry=entry,
            group=group,
            matches=[],
            text=rss_text,
            text_source="rss",
            selection_reason=(
                "technical_fallback_unverified"
            ),
            needs_ai_review=True,
            fetch_error=error,
        )

        stats[group]["selected"] += 1
        stats[group]["precaution"] += 1


# ============================================================
# SORTIES
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
# RÉSUMÉ
# ============================================================

print("\n==============================")
print("RÉSUMÉ PAR GROUPE")
print("==============================")


for group, s in stats.items():

    print(
        f"{group}: "
        f"{s['received']} reçus | "
        f"{s['recent']} récents | "
        f"{s['selected']} candidats | "
        f"{s['keyword_match']} match mot-clé | "
        f"{s['precaution']} précaution | "
        f"{s['businesswire_skipped']} "
        "BW langues écartées"
    )


precaution_count = sum(
    1
    for article in results
    if article.get("needs_ai_review")
)


bw_skipped_count = sum(
    s["businesswire_skipped"]
    for s in stats.values()
)


print("\n==============================")
print(f"CANDIDATS POUR L'IA: {len(results)}")
print(
    f"DONT CANDIDATS DE PRÉCAUTION: "
    f"{precaution_count}"
)
print(
    f"BUSINESS WIRE LANGUES ÉCARTÉES: "
    f"{bw_skipped_count}"
)
print(
    f"ÉCHECS TECHNIQUES JOURNALISÉS: "
    f"{len(unresolved)}"
)
print("==============================")


for article in results:

    groups = ", ".join(
        article["groups"]
    )

    keywords = ", ".join(
        article["matched_keywords"]
    )

    marker = (
        " [À ÉVALUER]"
        if article["needs_ai_review"]
        else ""
    )

    print(
        f"\n[{groups}]"
        f"{marker} "
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
        f"  raison: "
        f"{article['selection_reason']}"
    )

    print(
        f"  {article['url']}"
    )
