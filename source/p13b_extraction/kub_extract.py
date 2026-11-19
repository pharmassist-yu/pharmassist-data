"""P-13b spike: rule-based field extraction from TİTCK KÜB (SmPC) and KT (PIL) PDFs.

Usage (from the repository root):
    python source/p13b_extraction/kub_extract.py --manifest samples/sample_documents.csv --pdf-dir samples/pdf --out results/p13b

Reads each KÜB with pdfplumber, removes running headers/footers, splits the text
into QRD sections by heading number + keyword, and extracts the fields defined in
the Medication Data Schema (P-12a):

    product_name         KÜB 1
    active_ingredients   KÜB 2   (name, strength value/unit, "per" basis, raw text)
    known_effect_excip.  KÜB 2   (Yardımcı madde(ler))
    pharmaceutical_form  KÜB 3
    route                KÜB 4.2 (Uygulama şekli), fallback: form
    excipients           KÜB 6.1
    contraindications    KÜB 4.3 (section text + item list)
    interactions         KÜB 4.5 (section text)

From the KT it reads the "Etkin madde" and "Yardımcı maddeler" lines on page 1 so
the two documents can be cross-checked.

Everything is plain rules (no ML/LLM) so that the spike shows what pure parsing
can do. Output: one JSON per document plus extracted_fields.csv.

Pages without a usable text layer (scanned, or a broken hidden OCR layer) are
OCR'd with Tesseract using the Turkish model. Needs `tesseract` and poppler's
`pdftoppm` on PATH; set TESSDATA_DIR to the folder holding tur.traineddata
(https://github.com/tesseract-ocr/tessdata_fast). Without them those pages are
only flagged (stats.likely_scanned).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

import os
import subprocess
import tempfile

import pdfplumber

TESSDATA = os.environ.get("TESSDATA_DIR")  # folder with tur.traineddata

# --------------------------------------------------------------------------- text helpers

TR_UPPER = str.maketrans("ıiçğöşü", "IİÇĞÖŞÜ")


def fold(s: str) -> str:
    """Accent- and case-insensitive key for matching Turkish text.
    Length-preserving (one output char per input char) so match offsets can be
    used directly on the original text."""
    out = []
    for c in s:
        if c in "İI":
            out.append("i")
            continue
        d = unicodedata.normalize("NFKD", c)
        base = d[0] if d and not unicodedata.combining(d[0]) else c
        b = base.lower()
        out.append(b if len(b) == 1 else c)
    return "".join(out).replace("ı", "i")


PUA_MAP = {"\uf6da": "®", "\uf0d2": "®", "\uf0e2": "®", "\uf0b7": "•", "\uf0a7": "•", "\uf02d": "-",
           "\uf0b0": "°", "\uf0a3": "≤", "\uf0b3": "≥"}


def clean_line(s: str) -> str:
    """Normalise one extracted line: NFC, Symbol-font private-use characters, spaces."""
    s = unicodedata.normalize("NFC", s)
    s = "".join(PUA_MAP.get(c, "" if 0xE000 <= ord(c) <= 0xF8FF else c) for c in s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def text_layer_broken(text: str) -> bool:
    """True when a page has (almost) no usable text, or only non-ASCII letters survive
    (seen in old scanned KÜBs whose hidden OCR layer uses a non-embedded font)."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 80:
        return True
    ascii_share = sum(c.isascii() for c in letters) / len(letters)
    return ascii_share < 0.5


def ocr_page(path: Path, page_no: int) -> str:
    """OCR one page with Tesseract (Turkish model). Returns '' if Tesseract is missing."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "p"
            subprocess.run(["pdftoppm", "-r", "300", "-gray", "-f", str(page_no), "-l", str(page_no), "-png", str(path), str(img)],
                           check=True, capture_output=True)
            png = next(Path(tmp).glob("p*.png"))
            cmd = ["tesseract", str(png), "stdout", "-l", "tur", "--psm", "4"]
            if TESSDATA:
                cmd[1:1] = ["--tessdata-dir", TESSDATA]
            return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError, StopIteration):
        return ""


PAGE_NO_RE = re.compile(r"^(sayfa\s*)?\d{1,3}\s*(/|-|of|\s)\s*\d{1,3}$|^\d{1,3}$", re.I)


def read_pdf(path: Path) -> tuple[list[list[str]], dict]:
    """Return lines per page (headers/footers removed) and document stats."""
    pages: list[list[str]] = []
    n_chars = 0
    n_images = 0
    n_tables = 0
    ocr_pages: list[int] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=1.5, y_tolerance=3) or ""
            if text_layer_broken(text):
                text = ocr_page(path, page.page_number) or text
                ocr_pages.append(page.page_number)
            n_chars += len(text)
            n_images += len(page.images)
            try:
                n_tables += len(page.find_tables())
            except Exception:
                pass
            pages.append([clean_line(l) for l in text.splitlines() if clean_line(l)])
        n_pages = len(pdf.pages)

    # Running headers/footers: short lines that repeat on > 40% of pages, and page numbers.
    first_last = Counter()
    for lines in pages:
        for l in set(lines[:2] + lines[-2:]):
            first_last[re.sub(r"\d+", "#", l)] += 1
    repeated = {k for k, v in first_last.items() if n_pages >= 3 and v >= max(3, 0.4 * n_pages) and len(k) < 90}
    out = []
    for lines in pages:
        keep = []
        for i, l in enumerate(lines):
            edge = i < 2 or i >= len(lines) - 2
            if edge and (PAGE_NO_RE.match(l) or re.sub(r"\d+", "#", l) in repeated):
                continue
            keep.append(l)
        out.append(keep)
    stats = {
        "pages": n_pages,
        "chars": n_chars,
        "chars_per_page": round(n_chars / max(n_pages, 1)),
        "images": n_images,
        "tables_detected": n_tables,
        "likely_scanned": n_chars / max(n_pages, 1) < 200 or bool(ocr_pages),
        "ocr_pages": ocr_pages,
        "removed_header_footer_patterns": sorted(repeated)[:5],
    }
    return out, stats


# --------------------------------------------------------------------------- section split

# (key, number regex, keyword regex on folded text)
KUB_HEADINGS = [
    ("1", r"1", r"(beseri\s+)?tibbi\s+urun(un)?\s+adi|urun(un)?\s+adi"),
    ("2", r"2", r"kalitatif\s+ve\s+kantitatif"),
    ("3", r"3", r"farmasotik\s+form"),
    ("4", r"4", r"klinik\s+ozellik"),
    ("4.1", r"4\.\s?1", r"terapotik\s+endikasyon|endikasyon"),
    ("4.2", r"4\.\s?2", r"pozoloji"),
    ("4.3", r"4\.\s?3", r"kontrendikasyon"),
    ("4.4", r"4\.\s?4", r"ozel\s+kullanim|uyari"),
    ("4.5", r"4\.\s?5", r"etkilesim"),
    ("4.6", r"4\.\s?6", r"gebelik|ozel\s+popula"),
    ("4.7", r"4\.\s?7", r"arac\s+ve\s+makine|makine"),
    ("4.8", r"4\.\s?8", r"istenmeyen\s+etki"),
    ("4.9", r"4\.\s?9", r"doz\s+asimi"),
    ("5", r"5", r"farmakolojik\s+ozellik"),
    ("6", r"6", r"farmasotik\s+ozellik"),
    ("6.1", r"6\.\s?1", r"yardimci\s+madde"),
    ("6.2", r"6\.\s?2", r"gecimsizlik"),
    ("6.3", r"6\.\s?3", r"raf\s+omru"),
    ("7", r"7", r"ruhsat\s+sahibi"),
]


def find_sections(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Locate each heading (in order) and return {key: (start_line, end_line)}."""
    folded = [fold(l) for l in lines]
    found: list[tuple[str, int]] = []
    cursor = 0
    for key, num, kw in KUB_HEADINGS:
        pat = re.compile(rf"^\s*{num}\s*[\.\)]?\s*[-–:]?\s*[^\d].{{0,60}}?({kw})|^\s*{num}\s*[\.\)]?\s*[-–:]?\s*({kw})")
        for i in range(cursor, len(lines)):
            if pat.search(folded[i]):
                found.append((key, i))
                cursor = i + 1
                break
    spans = {}
    for idx, (key, start) in enumerate(found):
        end = found[idx + 1][1] if idx + 1 < len(found) else len(lines)
        spans[key] = (start, end)
    return spans


def section_body(lines, spans, key, *, include_subsections=False) -> list[str]:
    if key not in spans:
        return []
    start, end = spans[key]
    if include_subsections:
        nxt = [s for k, (s, _) in spans.items() if s > start and "." not in k and k != key]
        end = min(nxt) if nxt else len(lines)
    body = lines[start:end]
    # drop the heading text itself from the first line
    first = re.sub(r"^\s*\d+(\.\s?\d+)?\s*[\.\)]?\s*", "", body[0]) if body else ""
    head_kw = [kw for k, _, kw in KUB_HEADINGS if k == key][0]
    m = re.search(rf"({head_kw})[^\n]*?$", fold(first))
    rest = first[m.end():].strip(" :.-") if m and m.end() < len(first) else ""
    return ([rest] if rest else []) + body[1:]


# --------------------------------------------------------------------------- field parsers

UNIT = r"(mg|g|mcg|µg|μg|mikrogram|ng|IU|I\.U\.|ml|mL|mmol)"
NUM = r"\d+(?:[.,]\d+)*"
STRENGTH_RE = re.compile(rf"(?P<val>{NUM})\s*(?P<unit>{UNIT})(?P<per>\s*/\s*(?P<pv>{NUM})?\s*(?P<pu>ml|mL|g))?(?![a-zçğıöşü])", re.I)
BASIS_RE = re.compile(rf"(her|bir)\s+(?P<pv>{NUM})?\s*(?P<pu>ml|mL)\b|(olcek|ölçek)\s*\(\s*(?P<pv3>{NUM})\s*(?P<pu3>ml|mL)|(her|bir)\s+(?P<pu2>ml)\b|her\s+(bir\s+)?(?P<unit>film\s+kapl[ıi]\s+tablet|tablet|kaps[üu]l|supozituvar|sa[şs]e|po[şs]et|flakon|ampul)", re.I)
STOP = {"her", "bir", "ölçek", "olcek", "içerir", "icerir", "tablette", "tablet", "ml", "ml’de", "ml'de", "ml’lik", "ml'lik",
        "lik", "de", "da", "şurup", "surup", "olarak", "inn", "etkin", "madde", "maddeler", "ve"}


def _name_words(seg: str) -> str:
    seg = re.sub(r"\([^)]*\)", " ", seg)            # drop salt / equivalence notes
    seg = re.sub(r"\.{2,}|…+", " ", seg)             # dot leaders
    seg = STRENGTH_RE.sub(" ", seg)
    words = [w.strip(" .,:;*’'") for w in seg.split()]
    words = [w for w in words if w and re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", w)
             and fold(w).strip("’'") not in {fold(x) for x in STOP} and not re.match(r"^(ml|mL)[’']", w)]
    return " ".join(words)


def parse_section2(body: list[str]) -> dict:
    text = "\n".join(body)
    f = fold(text)
    m_act = re.search(r"etkin\s+madde", f)
    m_exc = re.search(r"yardimci\s+madde", f)
    a0 = m_act.end() if m_act else 0
    a1 = m_exc.start() if m_exc and m_exc.start() > a0 else len(text)
    act_text = re.sub(r"^\s*(\(ler\)|ler)?\s*:?", "", text[a0:a1]).strip()
    # some layouts put the basis line ("Her 5 mL (1 ölçek) şurup,") before "Etkin madde"
    pre = text[:m_act.start()] if m_act else ""
    exc_text = text[m_exc.end():] if m_exc else ""

    basis = None
    bm = BASIS_RE.search(pre + "\n" + act_text)
    if bm:
        if bm.group("unit"):
            basis = "1 " + bm.group("unit").lower()
        else:
            basis = f"{(bm.group('pv') or bm.group('pv3') or '1').replace(',', '.')} ml"

    joined = ""
    depth = 0
    for ch in act_text:
        depth += (ch == "(") - (ch == ")")
        joined += " " if (ch == "\n" and depth > 0) else ch
    segs = [x.strip() for x in re.split(r"\n|;|,(?!\d)", joined) if x.strip()]
    actives = []
    pending_name_for = None  # S11-style table: "100 mg" line followed by a name line
    for seg in segs:
        outside = re.sub(r"\([^)]*\)", lambda m: " " * len(m.group(0)), seg)
        hits = [sm for sm in STRENGTH_RE.finditer(outside) if sm.group("unit").lower() not in ("ml",)]
        name = _name_words(seg)
        if not hits:
            if pending_name_for is not None and name:
                pending_name_for["name_raw"] = name
                pending_name_for = None
            continue
        for sm in hits:
            item = {
                "name_raw": name,
                "strength_value": sm.group("val").replace(",", "."),
                "strength_unit": sm.group("unit"),
                "per": (f"{sm.group('pv') or 1} {sm.group('pu')}" if sm.group("pu") else None),
                "salt_or_equivalence_note": "; ".join(re.findall(r"\(([^)]*\d[^)]*)\)", seg)) or None,
                "line": seg[:200],
            }
            if item["per"] and not basis:
                basis = item["per"].replace("mL", "ml")
            actives.append(item)
            if not name:
                pending_name_for = item
    # a name-only line BEFORE the number (rare): fill empty names from previous segment
    actives = [a for a in actives if a["name_raw"]] + [a for a in actives if not a["name_raw"]]

    known_effect = []
    for line in exc_text.split("\n"):
        line = line.strip(" .:-•")
        fl = fold(line)
        if not line or fl in ("ler", "(ler)") or re.match(r"^(\(ler\)|ler)?\s*:?\s*$", fl):
            continue
        if re.search(r"yardimci\s+maddeler|bolum\s*6\.1|6\.1|bkz|icerikte\s+bulunan|^her\s+.*(ml|olcek)", fl):
            continue
        line = re.sub(r"\s*\.{2,}\s*|\s*…+\s*", " ", line)
        known_effect.append(re.sub(r"\s+", " ", line)[:150])
    return {"active_block": act_text[:1000], "per_basis": basis, "actives": actives, "known_effect_excipients": known_effect}


FORM_TERMS = [
    "süspansiyon hazırlamak için kuru toz", "oral süspansiyon hazırlamak için kuru toz", "infüzyon için çözelti",
    "infüzyon çözeltisi", "enjeksiyonluk çözelti", "film kaplı tablet", "efervesan tablet", "çiğneme tableti",
    "ağızda dağılan tablet", "oral çözelti", "oral süspansiyon", "oral damla", "tablet", "kapsül", "şurup", "süspansiyon",
    "supozituvar", "süpozituvar", "suppozituvar", "krem", "merhem", "jel", "damla", "toz", "saşe", "çözelti",
]


def parse_form(s3_body: list[str], product_name: str) -> tuple[str, str]:
    """Return (form, source). Prefer a short first line in KÜB 3 that is a form term."""
    first = (s3_body[0] if s3_body else "").strip(" .")
    if first and len(first.split()) <= 6 and any(fold(first).startswith(fold(t)) for t in FORM_TERMS):
        return first, "KÜB 3 first line"
    name_f = fold(product_name)
    for t in FORM_TERMS:  # longest first
        if fold(t) in name_f:
            return t, "product name (KÜB 3 has description only)"
    s3 = fold(" ".join(s3_body))
    for t in FORM_TERMS:
        if fold(t) in s3:
            return t, "KÜB 3 description"
    return "", "not found"


def first_sentence_block(body: list[str]) -> str:
    out = []
    for l in body:
        if out and (l[:1].islower() is False and len(" ".join(out)) > 15 and not out[-1].endswith(("-", ","))):
            break
        out.append(l)
    return " ".join(out).strip(" .")


ROUTE_RULES = [
    ("INTRAVENOUS", r"intraven|i\.v\.|\biv\b|infuzyon"),
    ("INTRAMUSCULAR", r"intramusk|i\.m\.|\bim\b"),
    ("RECTAL", r"rektal|makattan|supozituvar|suppozituvar"),
    ("ORAL", r"\boral\b|agizdan|yutul|agiz yoluyla|icilir"),
    ("SUBCUTANEOUS", r"subkutan|deri alt"),
    ("TOPICAL", r"topikal|cilde|haricen"),
    ("OPHTHALMIC", r"goze|okuler|oftalmik"),
    ("INHALATION", r"inhal"),
    ("NASAL", r"nazal|burun"),
]


def detect_routes(text: str) -> list[str]:
    f = fold(text)
    return [r for r, pat in ROUTE_RULES if re.search(pat, f)]


def parse_route(lines, spans, form: str, name: str = "") -> tuple[list[str], str]:
    body = section_body(lines, spans, "4.2")
    text = "\n".join(body)
    f = fold(text)
    m = re.search(r"uygulama\s+sekli\s*:?", f)
    snippet = ""
    if m:
        snippet = text[m.end(): m.end() + 400]
        snippet = re.split(r"\n\s*(ozel\s+populasyon|özel\s+popülasyon|böbrek|karaciğer|pediyatrik)", snippet, flags=re.I)[0]
        routes = detect_routes(snippet)
        if routes:
            return routes, "KÜB 4.2 Uygulama şekli"
    for src, txt in (("KÜB 4.2 Uygulama şekli (text)", snippet if m else ""), ("KÜB 3 form", form), ("product name", name)):
        routes = detect_routes(txt)
        if routes:
            return routes, src
    # tablets/syrups/suspensions are oral even when not stated
    if re.search(r"tablet|surup|suspansiyon|kapsul|oral|cozelti|sase|poset", fold(form)):
        return ["ORAL"], "inferred from form"
    return [], "not found"


BULLET_RE = re.compile(r"^([-•–*·▪●○]|\d+[\.\)]\s)")


def parse_list(body: list[str]) -> list[str]:
    """Split a section into items.
    Bullet mode (any bulleted line): each bullet is an item, a lead-in line before the
    first bullet is ignored, and un-bulleted lines continue the current item.
    Paragraph mode: a new item starts after a line that ends a sentence."""
    lines = [l.strip() for l in body if l.strip()]
    if any(BULLET_RE.match(l) for l in lines):
        items, cur = [], None
        for l in lines:
            if BULLET_RE.match(l):
                if cur:
                    items.append(cur)
                cur = BULLET_RE.sub("", l).strip()
            elif cur is not None:
                cur += " " + l
        if cur:
            items.append(cur)
        return [i.strip(" ;") for i in items if len(i) > 1]
    items, buf = [], ""
    for l in lines:
        if not buf or (buf.endswith((".", ";")) and l[:1].isupper()):
            if buf:
                items.append(buf)
            buf = l
        else:
            buf += " " + l
    if buf:
        items.append(buf)
    return [i.strip(" ;") for i in items if len(i.strip()) > 1]


def parse_excipients(body: list[str]) -> list[str]:
    out = []
    for l in body:
        for part in re.split(r",(?![^()]*\))|;", l):
            p = part.strip(" .•-–")
            if not p or re.fullmatch(r"\d+", p):
                continue
            if re.search(r"^(film kaplama|kaplama|cekirdek|tablet cekirdegi|kapsul kabugu|icerik)\s*:?\s*$", fold(p)):
                continue
            out.append(p)
    return out


# --------------------------------------------------------------------------- KT

def parse_kt(lines: list[str]) -> dict:
    head = lines[:60]
    text = "\n".join(head)
    f = fold(text)
    res = {"kt_active_line": "", "kt_excipient_line": ""}
    m = re.search(r"etkin\s+madde(ler)?\s*:?", f)
    if m:
        res["kt_active_line"] = re.split(r"\n\s*(yardımcı|yardimci)", text[m.end():], flags=re.I)[0].strip()[:400]
    m = re.search(r"yardimci\s+madde(ler)?\s*:?", f)
    if m:
        seg = text[m.end():]
        seg = re.split(r"\n\s*(bu\s+ilac|bu\s+ilacı|bu kullanma|bu talimatta)", seg, flags=re.I)[0]
        res["kt_excipient_line"] = " ".join(seg.split())[:800]
    return res


# --------------------------------------------------------------------------- main

def extract_kub(path: Path) -> dict:
    t0 = time.perf_counter()
    pages, stats = read_pdf(path)
    lines = [l for p in pages for l in p]
    spans = find_sections(lines)

    s1 = section_body(lines, spans, "1")
    product_name = " ".join(s1).strip()
    product_name = re.split(r"\s{2,}|2\.\s*KAL", product_name)[0][:200]

    s2 = parse_section2(section_body(lines, spans, "2"))
    form, form_src = parse_form(section_body(lines, spans, "3"), product_name)
    if not s2["per_basis"] and re.search(r"tablet|kapsul|supozituvar|suppozituvar|sase|poset", fold(form)):
        s2["per_basis"] = "PER_UNIT_DOSE (1 " + form.lower() + ")"
    routes, route_src = parse_route(lines, spans, form, product_name)
    ci_body = section_body(lines, spans, "4.3")
    ia_body = section_body(lines, spans, "4.5")
    exc_body = section_body(lines, spans, "6.1")

    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "stats": stats,
        "sections_found": sorted(spans, key=lambda k: spans[k][0]),
        "sections_missing": [k for k, *_ in KUB_HEADINGS if k not in spans],
        "product_name": product_name,
        "active_block": s2["active_block"],
        "per_basis": s2["per_basis"],
        "actives": s2["actives"],
        "known_effect_excipients": s2["known_effect_excipients"],
        "pharmaceutical_form": form,
        "form_source": form_src,
        "routes": routes,
        "route_source": route_src,
        "excipients": parse_excipients(exc_body),
        "contraindications_text": "\n".join(ci_body),
        "contraindication_items": parse_list(ci_body),
        "interactions_text": "\n".join(ia_body),
        "interactions_chars": len(" ".join(ia_body)),
        "seconds": round(time.perf_counter() - t0, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    (out / "json").mkdir(parents=True, exist_ok=True)
    rows = []
    with open(a.manifest, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sid = r["sample_id"]
            kub = Path(a.pdf_dir) / f"{sid}_KUB.pdf"
            kt = Path(a.pdf_dir) / f"{sid}_KT.pdf"
            if not kub.exists():
                print(f"{sid}: KÜB missing, skipped")
                continue
            res = extract_kub(kub)
            if kt.exists():
                kt_pages, kt_stats = read_pdf(kt)
                res.update(parse_kt([l for p in kt_pages for l in p]))
                res["kt_stats"] = kt_stats
            res["sample_id"] = sid
            (out / "json" / f"{sid}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
            rows.append({
                "sample_id": sid,
                "product_name": res["product_name"],
                "actives": " | ".join(f"{x['name_raw']} {x['strength_value']} {x['strength_unit']}" + (f" ({x['salt_or_equivalence_note']})" if x['salt_or_equivalence_note'] else "") for x in res["actives"]),
                "per_basis": res["per_basis"],
                "form": res["pharmaceutical_form"],
                "form_source": res["form_source"],
                "routes": ";".join(res["routes"]),
                "route_source": res["route_source"],
                "excipients": " | ".join(res["excipients"]),
                "known_effect_excipients": " | ".join(res["known_effect_excipients"]),
                "contraindication_items": len(res["contraindication_items"]),
                "interactions_chars": res["interactions_chars"],
                "sections_missing": ";".join(res["sections_missing"]),
                "pages": res["stats"]["pages"],
                "chars_per_page": res["stats"]["chars_per_page"],
                "likely_scanned": res["stats"]["likely_scanned"],
                "seconds": res["seconds"],
            })
            print(f"{sid}: {res['seconds']}s, missing sections: {res['sections_missing']}")
    with open(out / "extracted_fields.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
