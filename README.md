# pharmassist
PharmAssist: AI-supported personalized medication information system. Checks drug interactions, contraindications and equivalent medication candidates based on a user's health profile. YU Senior Project 2026-2027.


## TİTCK KÜB/KT data extraction

The scripts in `source/` collect the TİTCK KÜB/KT listing, download a sample of KÜB PDFs, and extract sections and structured fields from those PDFs.

### Setup

From the repository root, create a Python 3.9 virtual environment and install the dependencies:

```bash
python3.9 -m venv .venv
source .venv/bin/activate
python -m pip install requests pdfplumber
```

### Run the pipeline

From the repository root:

```bash
python source/listele.py
python source/ornek_indir.py 20
cd ornek
python ../source/ayir2.py
python ../source/ayir3.py
cd ..
```

To try only the first page of the listing, run `python source/listele.py --test` from the repository root. This writes a partial `kubkt_liste.csv` and overwrites any existing copy.

Downloaded PDFs and extraction results are saved locally under `ornek/`. Keep PDFs, CSV and JSON files, extracted text, `kubkt_sayfa.html`, and credentials out of Git. The pregnancy and lactation labels are experimental, keyword-based outputs that require manual verification.
