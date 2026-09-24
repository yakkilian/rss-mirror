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
