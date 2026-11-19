---
title: "P-13b Spike: Extract Fields from Sample KÜB/KT Documents"
---

19 November 2026 · Yankı · PharmAssist

## Summary

- **Extraction was run on 16 products (16 KÜB + 16 KT = 32 PDFs).** The set covers tablets, film-coated tablets, syrups, suspensions, a powder for suspension, an oral solution, a suppository and an IV infusion. It includes single products, 2- and 3-ingredient combinations, and same-name products in different strengths (Augmentin 500/875, Abilify 5/10). Documents date from 2014 to 2026 and come from 4 companies.
- **Method:** Python + pdfplumber with plain rules: QRD section headings, then field-specific patterns. Tesseract OCR (Turkish model) is used only as a fallback for pages whose text layer is unusable. No LLM was used.
- **Identity and composition fields are automatable.** After one tuning round, name, composition and strength, strength basis, form, route and both excipient lists were correct in **88–100%** of documents. The only real failures came from the scanned 2014 document.
- **Contraindications and interactions can be cut out reliably, but not structured.** The KÜB 4.3 and 4.5 sections were captured with correct boundaries in 15/16 documents. Turning them into schema rows (ci_type, interactant, severity) cannot be done with rules. This is where most of the manual work is.
- **Caveat:** the rules were tuned on these same 16 documents. The first, untuned version scored only 0–31% on composition, basis, form, known-effect excipients and interactions. Expect unseen documents to score between the two versions until a held-out test is run (see §6).
- **Effort:** the machine time is negligible (about 1.2 s per born-digital KÜB, about 38 s per scanned one). The estimated human time is **about 3.5 min per product** for checking identity/composition fields and **about 22 min per product** including manual structuring of contraindications and interactions. For 6,000 products that is about **350 h** and about **2,250 h**.
- **Recommendation for Sprint 5:** keep a **Python** pipeline in the data repository. Auto-extract identity/composition/excipients for all products, but structure 4.3/4.5 only for a **priority subset**, deduplicated by identical text. Run a separate short spike on LLM-assisted drafting of 4.3/4.5 rows with human approval.

## 1. Sample set

| ID | Product (KÜB 1) | Form | Variety | KÜB date |
|---|---|---|---|---|
| S01 | PAROL 500 mg tablet | tablet | single | 2020 |
| S02 | PAROL 120 mg/5 mL oral süspansiyon | suspension | single | 2026 |
| S03 | PAROL PLUS 250/150/50 mg tablet | tablet | 3 actives | 2026 |
| S04 | PAROL-K 500 mg/10 mg tablet | tablet | 2 actives, salt equivalence | 2026 |
| S05 | PAROL 200 mg supozituvar | suppository | single, rectal | 2026 |
| S06 | PAROL 10 mg/ml infüzyon | IV solution | single, IV | 2019 |
| S07 | AUGMENTİN 500/125 mg film kaplı tablet | film-coated tablet | 2 actives | 2024 |
| S08 | AUGMENTİN 875/125 mg film kaplı tablet | film-coated tablet | same name, other strength | 2024 |
| S09 | AUGMENTİN-BID 400+57 mg/5 ml kuru toz | powder for suspension | 2 actives | 2023 |
| S10 | PEDİFEN 100 mg/5 ml pediatrik şurup | syrup | single | 2022 |
| S11 | PEDİFEN COLD&FLU 100+15+1 mg/5 mL şurup | syrup | 3 actives | 2025 |
| S12 | PEDİFEN pediatrik şurup (old version) | syrup | single, **scanned** | 2014 |
| S13 | ABILIFY 5 mg tablet | tablet | single | 2026 |
| S14 | ABILIFY 10 mg tablet | tablet | same name, other strength | 2026 |
| S15 | ABILIFY 1 mg/ml oral çözelti | oral solution | single | 2026 |
| S16 | KLACİD 500 mg film kaplı tablet | film-coated tablet | single | 2026 |

Documents were found by searching the TİTCK KÜB/KT portal in the browser (method A from P-13). They were then downloaded once by `download_samples.ps1`, one request every 5 seconds. URLs are listed in `samples/sample_documents.csv`.

## 2. Method

1. **Text extraction:** pdfplumber reads each page and removes running headers, footers and page numbers. If a page has fewer than 80 letters, or fewer than half of its letters are ASCII (a broken OCR layer), the page is rendered at 300 dpi and read with Tesseract (`tur`).
2. **Section split:** the script finds the QRD headings (1, 2, 3, 4.1–4.9, 5, 6, 6.1–6.3, 7) by number + keyword, in document order, matching case- and accent-insensitively.
3. **Field rules:**

| Field (schema P-12a) | Source | Rule |
|---|---|---|
| product_name | KÜB 1 | Section text |
| active ingredients + strength | KÜB 2 "Etkin madde" | Number + unit; name from the same line (or the next line for table layouts); text in parentheses kept as salt/equivalence note |
| strength basis | KÜB 2 | "Her 5 ml'de", "Bir ölçek (5 mL)", "10 mg/ml", "Her tablette"; otherwise per unit dose for solid forms |
| known-effect excipients | KÜB 2 "Yardımcı madde(ler)" | One per line, dot leaders removed |
| pharmaceutical form | KÜB 3 | First line if it starts with a known form term; otherwise the form term in the product name |
| route | KÜB 4.2 "Uygulama şekli" | Keyword map (oral/ağızdan, rektal/supozituvar, intravenöz/infüzyon …); fallbacks: form, name |
| excipients | KÜB 6.1 | One per line or comma; sub-headings ("Film kaplama") dropped |
| contraindications | KÜB 4.3 | Section text + item split (bullets, otherwise sentences) |
| interactions | KÜB 4.5 | Section text |
| KT cross-check | KT page 1 | "Etkin madde" and "Yardımcı maddeler" lines |

4. **Checking:** I typed the ground truth into `results/gold.json` from the documents. For born-digital PDFs I took it from the text layer, after comparing that layer with rendered pages. For S12 I typed it from the page images. `score.py` compares every field. It checks the 4.3/4.5 boundaries against a second, independent extractor (poppler `pdftotext`), so that check is not circular.

## 3. Results per field

| Field | Correct (tuned v2) | Usable incl. partial | First pass (v1, untuned) |
|---|---|---|---|
| Product name | **94%** (15/16) | 94% | 88% |
| Active ingredients + strength | **100%** | 100% | 31% |
| Strength basis (per tablet / per 5 ml …) | **100%** | 100% | 31% |
| Known-effect excipients (KÜB 2) | **94%** | 100% | 25% |
| Pharmaceutical form | **88%** | 100% | 31% |
| Route | **100%** | 100% | 88% |
| Excipients (KÜB 6.1) | **94%** | 100% | 94% |
| Contraindications section captured (4.3) | **94%** | 100% | 94% |
| Contraindication items split correctly | **94%** | 94% | 69% |
| Interactions section captured (4.5) | **94%** | 100% | 0% |
| Contraindications → schema rows (ci_type, mapped condition/ingredient) | not automated | — | — |
| Interactions → schema rows (interactant, severity) | not automated | — | — |

Every remaining failure in v2 is in **S12 (scanned)** or in the **form ambiguity of S10/S12**:

- **S12 (OCR):** "5ml" was read as "59ml", "%70" as "7094", and the bullets came out as "»e", so the 10 contraindications collapsed into 1 item.
- **S10/S12:** KÜB 3 has no form term, and its description says *süspansiyon* while the name says *şurup*. Partial means the value is usable but a person has to fix it or make a decision.

Per-document details are in `results/field_scores.csv`, and the extracted values are in `results/extracted_fields.csv` and `results/json/`.

KÜB 6.1 and the KT excipient line agreed for 14/16 products. The other two differ only in naming ("Agar BPC 54 PDR" vs "agar"; "Selüloz mikrokristalin" vs "mikrokristalin selüloz"). The KT is therefore a useful second check, but its names need normalising.

## 4. Problems found

1. **Scanned PDF with a broken text layer (S12, 2014).** It has a hidden OCR layer with a non-embedded font, so only Turkish letters come out of the text layer. It needs OCR: about 38 s per document, with character errors in numbers (critical for strengths) and lost bullet structure. In this sample 1/16 documents was affected; older documents are probably affected more often.
2. **Heading variation.** Headings appear as "4.5 Diğer tıbbi ürünler ile etkileşimler…" (the keyword is not at the start), as "4.3." vs "4.3", split across lines ("Uygulama / şekli"), and sometimes missing (4.9 in S12, 6.3 in S13).
3. **Tables and layout.** S11's composition is a two-column table that comes out as alternating "100 mg" / "İbuprofen" lines. Other layouts use dot leaders ("Amoksisilin ……… 500 mg") and decimal commas ("12,5 mg"), which break a comma-based split.
4. **Many ways of writing composition.** Salt notes appear in parentheses before or after the strength, can wrap across lines, and use "eşdeğer" or "… olarak". The strength basis is written as "Her 5 ml'de", "Bir ölçek (5 mL)", "10mg/ml", "Her tablette", or left implicit.
5. **Missing or conflicting form.** KÜB 3 sometimes contains only a description (S05, S10, S12), and in S10/S12 the description conflicts with the product name. A person has to decide.
6. **Font artefacts.** Old Word templates encode "®" as a private-use character (U+F6DA), and an e-signature footer appears on every page. Both have to be cleaned.
7. **Contraindication lists.** Some use bullets and some use paragraphs. There are lead-in lines ("… aşağıdaki durumlarda kontrendikedir:") and continuation paragraphs. Items mix conditions, populations and concomitant drugs, so classifying them into `ci_type` needs judgement.
8. **Interactions are long free text** (2,100–18,400 characters, median about 4,500). Interactants, classes and severity are written in prose, so rules cannot produce INTERACTION rows.
9. **Duplicate texts.** 3 of 16 products share 4.3/4.5 text with another product (Augmentin 500/875; Abilify tablets and oral solution). That's work that can be reused.
10. **Overfitting risk.** v2 rules were developed on these 16 documents, so accuracy on new documents is not yet known.

## 5. Time per record and effort for 6,000 records

**Measured (machine):** about 1.2 s per born-digital KÜB (max 2.0 s), about 38 s for the 15-page scanned KÜB, 92 s in total for all 32 PDFs, most of it OCR of the old scanned PEDİFEN KÜB and KT. Downloading takes 5 s per file at the polite rate.

**Estimated (human):** this was not timed on team members. The estimates are based on what each step involves in these documents, and should be replaced by measured times (see §6).

| Step | Per product | Basis |
|---|---|---|
| A. Check identity/composition/excipients against source excerpts | 3 min (8 min if scanned) | 7 short fields, values shown next to source text |
| B. Structure contraindications into rows | about 6 min | about 1 min × 5.9 items on average (range 1–21) |
| C. Structure interactions into rows | about 13 min | about 2.5 min per 1,000 characters × 5,400 characters on average |
| **Total if everything is done by hand** | **about 22 min** | |

| Scenario for 6,000 products (assume 10% scanned) | Effort |
|---|---|
| Machine extraction (all) | about 8 h compute + about 17 h download (12,000 files at 5 s) |
| A only, every product | **about 350 h** |
| A + B + C, every product | **about 2,250 h** |
| A + B + C with identical-text dedupe (−19% on B+C, as in the sample) | about 1,900 h |
| A for all + B + C for a priority list of 500 products | about 350 h + about 160 h ≈ **510 h** |

At about 40 team-hours per week on data work, full structuring of 6,000 products is not feasible in the project timeline. The priority-list scenario is.

## 6. Recommendation for Sprint 5

1. **Language and method:** **Python** in the data repository, using pdfplumber with a Tesseract (`tur`) fallback and poppler `pdftotext` as a cross-check. The PDF, OCR and data tooling is stronger in Python than in Java/PDFBox, and the spike code can be reused directly. The pipeline should output CSV/JSON that a loader imports into PostgreSQL (SCRUM-61). The Spring backend doesn't need to parse PDFs.
2. **Store everything as UNVERIFIED first** (schema §3.1). Keep the full 4.3/4.5 text as `source_excerpt_tr`, and record `MEDICATION_SECTION_COVERAGE` honestly (NOT_EXTRACTED where 4.3/4.5 rows are missing), so the app can say "cannot check" instead of "no issue".
3. **Scope:** do step A for all products in scope. Do steps B and C only for a **priority list** (most-prescribed active ingredients). Deduplicate by identical 4.3/4.5 text before anyone structures it.
4. **Two short tasks before committing the Sprint 5 plan:**
   - **Held-out test:** run the v2 extractor on 20 new KÜBs not used for tuning, to get unbiased success rates.
   - **Timing:** have 2 team members each check and structure 5 records with a stopwatch, and replace the estimates in §5.
5. **Separate spike to consider:** LLM-assisted drafting of contraindication/interaction rows. Each row would cite its source excerpt and be approved by a person. If it brings B+C below about 8 min per product, the priority list can grow. This was not tested here.
6. **Scanned documents:** detect them automatically (already implemented), send them to a manual queue, and check whether TİTCK has a newer born-digital version first.

## 7. Files in the repository

| Path | Content |
|---|---|
| `samples/sample_documents.csv` | 16 products with portal names and KÜB/KT URLs |
| `samples/pdf/` | Downloaded PDFs (git-ignored: CONTRIBUTING §4, no bulk KÜB/KT) |
| `source/p13b_extraction/download_samples.ps1` / `.py` | Polite sample downloader (PowerShell version works around Python's certificate error) |
| `source/p13b_extraction/kub_extract.py` | Extractor (v2) |
| `source/p13b_extraction/score.py` | Scoring against `gold.json` |
| `source/p13b_extraction/requirements.txt` | Python dependencies |
| `results/p13b/extracted_fields.csv`, `json/` | Extracted values per document |
| `results/p13b/gold.json` | Manual ground truth |
| `results/p13b/field_scores.csv`, `summary.csv` | Per-document and per-field results (v2) |
| `results/p13b/summary_v1_untuned.csv` | First-pass results for comparison |

**How to re-run** (from the repository root):

```
pip install -r source/p13b_extraction/requirements.txt
python source/p13b_extraction/kub_extract.py --manifest samples/sample_documents.csv --pdf-dir samples/pdf --out results/p13b
python source/p13b_extraction/score.py --results results/p13b --pdf-dir samples/pdf
```

OCR and scoring also need Tesseract with the Turkish model (`tur.traineddata`, folder given with `TESSDATA_DIR`) and poppler (`pdftoppm`, `pdftotext`) on PATH. Without Tesseract, scanned pages are only flagged.
