from pathlib import Path
import requests

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
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8",
}

successes = 0

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

if successes == 0:
    raise SystemExit("Aucun flux n'a pu être récupéré")
