"""P-13b: download the KÜB/KT sample PDFs listed in samples/sample_documents.csv.

Polite by design (see P-13 spike report): one request every 5 seconds, a
User-Agent that identifies the project, and files that already exist are skipped.
Only meant for the small P-13b sample set, not for bulk collection.

Usage (from the repository root):
    python source/p13b_extraction/download_samples.py
"""
import csv
import time
import urllib.request
from pathlib import Path

# titck.gov.tr does not send its intermediate certificate, so Python's bundled CA
# list fails with CERTIFICATE_VERIFY_FAILED. truststore makes Python verify with the
# operating system's certificate store (which can fetch the missing intermediate),
# the same way the browser does. Verification stays ON.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    print("Tip: if you get CERTIFICATE_VERIFY_FAILED, run:  pip install truststore")

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "samples" / "sample_documents.csv"
OUT = ROOT / "samples" / "pdf"
DELAY_S = 5
UA = "PharmAssist-SeniorProject/0.1 (academic, non-commercial; P-13b sample download)"


def fetch(url: str, dest: Path) -> None:
    req = urllib.request.Request(url.replace(" ", "%20"), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if not data.startswith(b"%PDF"):
        raise ValueError("response is not a PDF (blocked or moved?)")
    dest.write_bytes(data)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        for kind, col in (("KUB", "kub_url"), ("KT", "kt_url")):
            dest = OUT / f"{row['sample_id']}_{kind}.pdf"
            if dest.exists():
                print(f"skip  {dest.name}")
                continue
            try:
                fetch(row[col], dest)
                print(f"ok    {dest.name}  {dest.stat().st_size // 1024} KB")
            except Exception as e:  # keep going, report at the end
                print(f"FAIL  {dest.name}: {e}")
            time.sleep(DELAY_S)


if __name__ == "__main__":
    main()
