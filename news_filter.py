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

# Texte effectivement transmis ensuite à l'IA.
# On garde nettement plus que les 3 000 caractères de la V1,
# tout en évitant des fichiers inutilement énormes.
MAX_CONTENT_CHARS = 15000

# Le chapô / contenu RSS reste disponible séparément.
MAX_RSS_CHARS = 5000

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

        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            low = key.lower()

            if low.startswith("utm_"):
                continue

            if low in {"feedref", "oc"}:
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
    /en/, /fr/, /de/, /it/, /zh-CN/.
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
            url = freshrss_url(feed_url, offset=None)
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
        or entry.get("created")
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


def entry_raw_date(entry):
    return (
        entry.get("published")
        or entry.get("updated")
        or entry.get("created")
        or ""
    )


def published_at_iso(entry):
    dt = entry_datetime(entry)

    if dt is None:
        return ""

    return dt.isoformat()


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
# MÉTADONNÉES DE SOURCE
# ============================================================

def source_name(entry, url):
    """
    Essaie d'obtenir une source lisible depuis le flux.
    À défaut, utilise le domaine de l'URL.
    """
    source = entry.get("source")

    if source:
        try:
            title = source.get("title")
            if title:
                return str(title).strip()
        except Exception:
            pass

        if isinstance(source, str) and source.strip():
            return source.strip()

    try:
        host = urlsplit(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def feed_entry_id(entry):
    return (
        entry.get("id")
        or entry.get("guid")
        or ""
    )


def feed_guid(entry):
    return (
        entry.get("guid")
        or entry.get("id")
        or ""
    )


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
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def truncate_text(text, max_chars):
    text = (text or "").strip()

    if len(text) <= max_chars:
        return text, False

    return text[:max_chars].rstrip(), True


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
# AJOUT / FUSION D'UN CANDIDAT
# ============================================================

def content_payload(title, rss_text, full_text, fulltext_success):
    """
    Construit le contenu réellement fourni à l'IA.

    Priorité:
    texte intégral extrait > contenu RSS > titre seul.
    """
    if fulltext_success and full_text.strip():
        original = full_text.strip()
        content, truncated = truncate_text(
            original,
            MAX_CONTENT_CHARS,
        )
        return {
            "content": content,
            "content_source": "fulltext",
            "content_truncated": truncated,
            "content_length_chars": len(original),
        }

    if rss_text.strip():
        original = rss_text.strip()
        content, truncated = truncate_text(
            original,
            MAX_CONTENT_CHARS,
        )
        return {
            "content": content,
            "content_source": "rss",
            "content_truncated": truncated,
            "content_length_chars": len(original),
        }

    original = title.strip()
    content, truncated = truncate_text(
        original,
        MAX_CONTENT_CHARS,
    )
    return {
        "content": content,
        "content_source": "title",
        "content_truncated": truncated,
        "content_length_chars": len(original),
    }


def content_rank(source):
    return {
        "title": 0,
        "rss": 1,
        "fulltext": 2,
    }.get(source, -1)


def add_selected(
    selected,
    entry,
    group,
    matches,
    rss_text,
    full_text,
    fulltext_success,
    selection_reason,
    needs_ai_review=False,
    fetch_error="",
):
    url = entry.get("link", "").strip()
    title = entry.get("title", "").strip()

    if not url or not title:
        return

    key = canonical_key(url)

    summary_rss, summary_truncated = truncate_text(
        rss_text,
        MAX_RSS_CHARS,
    )

    payload = content_payload(
        title=title,
        rss_text=rss_text,
        full_text=full_text,
        fulltext_success=fulltext_success,
    )

    new_item = {
        "title": title,
        "url": url,
        "source": source_name(entry, url),
        "published_at": published_at_iso(entry),
        "published_raw": entry_raw_date(entry),
        "published_at_basis": (
            "feed" if published_at_iso(entry) else "unknown"
        ),
        "feed_entry_id": feed_entry_id(entry),
        "guid": feed_guid(entry),
        "groups": [group],
        "matched_keywords": list(matches),
        "summary_rss": summary_rss,
        "summary_rss_truncated": summary_truncated,
        "content": payload["content"],
        "content_source": payload["content_source"],
        "content_truncated": payload["content_truncated"],
        "content_length_chars": payload["content_length_chars"],
        "fulltext_fetch_success": bool(fulltext_success),
        "fulltext_fetch_error": (
            "" if fulltext_success else fetch_error
        ),
        "selection_reason": selection_reason,
        "selection_reasons": [selection_reason],
        "needs_ai_review": bool(needs_ai_review),
    }

    if key not in selected:
        selected[key] = new_item
        return

    existing = selected[key]

    # Groupes / mots-clés / raisons de sélection.
    if group not in existing["groups"]:
        existing["groups"].append(group)

    for match in matches:
        if match not in existing["matched_keywords"]:
            existing["matched_keywords"].append(match)

    if selection_reason not in existing["selection_reasons"]:
        existing["selection_reasons"].append(selection_reason)

    # Si au moins une voie a confirmé le candidat, on ne le laisse
    # pas marqué comme candidat de précaution global.
    existing["needs_ai_review"] = (
        existing["needs_ai_review"]
        and bool(needs_ai_review)
    )

    # Conserver le meilleur chapô RSS disponible.
    if len(new_item["summary_rss"]) > len(existing["summary_rss"]):
        existing["summary_rss"] = new_item["summary_rss"]
        existing["summary_rss_truncated"] = new_item[
            "summary_rss_truncated"
        ]

    # Conserver le contenu le plus riche disponible.
    old_rank = content_rank(existing["content_source"])
    new_rank = content_rank(new_item["content_source"])

    should_replace_content = (
        new_rank > old_rank
        or (
            new_rank == old_rank
            and new_item["content_length_chars"]
            > existing["content_length_chars"]
        )
    )

    if should_replace_content:
        for field in (
            "content",
            "content_source",
            "content_truncated",
            "content_length_chars",
        ):
            existing[field] = new_item[field]

    # Une récupération réussie prime sur un échec rencontré via
    # une autre occurrence du même article.
    existing["fulltext_fetch_success"] = (
        existing["fulltext_fetch_success"]
        or new_item["fulltext_fetch_success"]
    )

    if existing["fulltext_fetch_success"]:
        existing["fulltext_fetch_error"] = ""
    elif (
        new_item["fulltext_fetch_error"]
        and new_item["fulltext_fetch_error"]
        not in existing["fulltext_fetch_error"]
    ):
        if existing["fulltext_fetch_error"]:
            existing["fulltext_fetch_error"] += "; "
        existing["fulltext_fetch_error"] += new_item[
            "fulltext_fetch_error"
        ]

    # Compléter les métadonnées manquantes si une autre occurrence
    # du même article est plus informative.
    for field in (
        "source",
        "published_at",
        "published_raw",
        "feed_entry_id",
        "guid",
    ):
        if not existing.get(field) and new_item.get(field):
            existing[field] = new_item[field]

    existing["published_at_basis"] = (
        "feed" if existing.get("published_at") else "unknown"
    )


# ============================================================
# TRAITEMENT
# ============================================================

selected = {}

# Ce fichier reste un diagnostic technique.
# Ses articles peuvent désormais AUSSI être présents
# dans candidates.json.
unresolved = []

# Tous les articles récents sont regroupés ici afin que le texte
# intégral soit tenté une seule fois par URL, y compris pour
# ICTj news / ICT best avant l'étape IA.
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
    "à analyser / enrichir en texte intégral"
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
# SÉLECTION / ENRICHISSEMENT
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

        title = entry.get("title", "").strip()

        # ----------------------------------------------------
        # ICTj news / ICT best:
        # tout passe à l'étape IA.
        # On tente désormais aussi de fournir le texte intégral.
        # ----------------------------------------------------
        if group in ("ICTj news", "ICT best"):
            add_selected(
                selected=selected,
                entry=entry,
                group=group,
                matches=[],
                rss_text=rss_text,
                full_text=full_text,
                fulltext_success=success,
                selection_reason="all_from_group",
                needs_ai_review=False,
                fetch_error=error,
            )

            stats[group]["selected"] += 1
            continue

        # ----------------------------------------------------
        # Suisse / ICT:
        # filtrage lexical sur le meilleur contenu disponible.
        # ----------------------------------------------------
        if group == "Suisse":
            keywords = SWISS_IT_KEYWORDS
        else:
            keywords = ICT_SWISS_KEYWORDS

        # ----------------------------------------------------
        # TEXTE INTÉGRAL DISPONIBLE
        # ----------------------------------------------------
        if success:
            # Le RSS est inclus en complément: certaines pages web
            # sont extraites imparfaitement alors que le chapô est bon.
            searchable = (
                f"{title}\n{full_text}\n{rss_text}"
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
                    rss_text=rss_text,
                    full_text=full_text,
                    fulltext_success=True,
                    selection_reason="keyword_fulltext",
                    needs_ai_review=False,
                    fetch_error="",
                )

                stats[group]["selected"] += 1
                stats[group]["keyword_match"] += 1

            continue

        # ----------------------------------------------------
        # TEXTE INTÉGRAL INACCESSIBLE
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
            add_selected(
                selected=selected,
                entry=entry,
                group=group,
                matches=matches,
                rss_text=rss_text,
                full_text="",
                fulltext_success=False,
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
                    "source": source_name(entry, url),
                    "published_at": published_at_iso(entry),
                    "published_raw": entry_raw_date(entry),
                    "feed_entry_id": feed_entry_id(entry),
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
        # Au lieu de jeter l'article, on le transmet à l'IA
        # avec son chapô RSS comme candidat de précaution.
        # ----------------------------------------------------
        diagnostic = {
            "title": title,
            "url": url,
            "group": group,
            "source": source_name(entry, url),
            "published_at": published_at_iso(entry),
            "published_raw": entry_raw_date(entry),
            "feed_entry_id": feed_entry_id(entry),
            "fetch_error": error,
            "rss_excerpt": rss_text[:3000],
        }

        # ----------------------------------------------------
        # Business Wire:
        # parmi ces candidats NON CONFIRMÉS uniquement,
        # on évite de transmettre toutes les traductions.
        # FR + EN conservés.
        # Les autres langues restent dans unresolved.json.
        # ----------------------------------------------------
        if skip_unverified_businesswire_translation(url):
            diagnostic[
                "candidate_action"
            ] = "excluded_non_fr_en_businesswire"

            unresolved.append(diagnostic)
            stats[group]["businesswire_skipped"] += 1
            continue

        diagnostic[
            "candidate_action"
        ] = "included_for_ai_review"

        unresolved.append(diagnostic)

        add_selected(
            selected=selected,
            entry=entry,
            group=group,
            matches=[],
            rss_text=rss_text,
            full_text="",
            fulltext_success=False,
            selection_reason="technical_fallback_unverified",
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

fulltext_count = sum(
    1
    for article in results
    if article.get("content_source") == "fulltext"
)

rss_count = sum(
    1
    for article in results
    if article.get("content_source") == "rss"
)

title_only_count = sum(
    1
    for article in results
    if article.get("content_source") == "title"
)

truncated_count = sum(
    1
    for article in results
    if article.get("content_truncated")
)

print("\n==============================")
print(f"CANDIDATS POUR L'IA: {len(results)}")
print(
    f"DONT CANDIDATS DE PRÉCAUTION: "
    f"{precaution_count}"
)
print(
    f"CONTENU IA: {fulltext_count} texte intégral | "
    f"{rss_count} RSS | {title_only_count} titre seul"
)
print(
    f"CONTENUS TRONQUÉS À {MAX_CONTENT_CHARS} CAR.: "
    f"{truncated_count}"
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
    groups = ", ".join(article["groups"])
    keywords = ", ".join(article["matched_keywords"])

    marker = (
        " [À ÉVALUER]"
        if article["needs_ai_review"]
        else ""
    )

    trunc_marker = (
        " [TRONQUÉ]"
        if article["content_truncated"]
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
        f"  source: {article['source']}"
    )
    print(
        f"  publié: {article['published_at'] or article['published_raw']}"
    )
    print(
        f"  contenu IA: {article['content_source']}"
        f"{trunc_marker}"
    )
    print(
        f"  longueur source: "
        f"{article['content_length_chars']} caractères"
    )
    print(
        f"  raison: "
        f"{article['selection_reason']}"
    )
    print(
        f"  {article['url']}"
    )
