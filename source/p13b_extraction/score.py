"""P-13b: compare extracted fields with the manual ground truth (results/gold.json).

Usage (from the repository root):
    python source/p13b_extraction/score.py --results results/p13b --pdf-dir samples/pdf

Writes results/field_scores.csv (one row per document x field) and
results/summary.csv (success rate per field), and prints the summary.

Outcome per field: CORRECT, PARTIAL (usable but needs a manual fix or decision), WRONG.
The 4.3 / 4.5 section boundaries are checked against a second, independent text
extractor (poppler's pdftotext) so the check is not circular.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kub_extract import fold  # noqa: E402


def norm(s: str) -> str:
    s = fold(s).replace("®", "")
    s = re.sub(r"\s*\d[\d.,]*\s*(mg|g|mcg|µg)(/ml)?\s*$", "", s)  # trailing quantity
    s = re.sub(r"[\s.,;:*]+", " ", s)
    return re.sub(r"\s+", "", s)  # ignore spacing differences ("5 ml" vs "5ml")


def basis_cat(b):
    if not b:
        return None
    b = fold(b)
    if "per_unit_dose" in b or "tablet" in b or "supozituvar" in b:
        return "UNIT"
    m = re.match(r"([\d.]+)\s*ml", b)
    return f"{float(m.group(1)):g} ml" if m else b


def section_by_pdftotext(pdf: Path, num: str, next_num: str) -> str:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    lines = txt.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(rf"^\s*{re.escape(num)}\.?\s+\S", l)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if re.match(rf"^\s*{re.escape(next_num)}\.?\s+\S", lines[i])), len(lines))
    return " ".join(lines[start + 1:end])


def words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]{4,}", fold(s))


def boundary_ok(ours: str, ref: str) -> str:
    """Compare first/last 6 words of the section between the two extractors."""
    a, b = words(ours), words(ref)
    if not a or not b:
        return "WRONG" if not a else "PARTIAL"
    head = a[:6] == b[:6]
    tail = a[-6:] == b[-6:]
    overlap = len(set(a) & set(b)) / max(len(set(b)), 1)
    if head and tail:
        return "CORRECT"
    return "PARTIAL" if overlap > 0.8 else "WRONG"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--pdf-dir", required=True)
    a = ap.parse_args()
    res_dir = Path(a.results)
    gold = json.loads((res_dir / "gold.json").read_text(encoding="utf-8"))
    rows = []
    for sid, g in gold.items():
        if sid.startswith("_"):
            continue
        d = json.loads((res_dir / "json" / f"{sid}.json").read_text(encoding="utf-8"))
        ocr = bool(d["stats"].get("ocr_pages"))

        def add(field, outcome, extracted, expected, note=""):
            rows.append({"sample_id": sid, "field": field, "outcome": outcome, "extracted": extracted,
                         "expected": expected, "ocr": ocr, "note": note})

        # product name
        add("product_name", "CORRECT" if norm(d["product_name"]) == norm(g["product_name"]) else "WRONG", d["product_name"], g["product_name"])

        # composition: names + values (+ salt note when the KÜB has one)
        got = sorted((norm(x["name_raw"]), x["strength_value"].rstrip("0").rstrip(".") if "." in x["strength_value"] else x["strength_value"]) for x in d["actives"])
        exp = sorted((norm(n), v) for n, v in g["actives"])
        has_note = any(x.get("salt_or_equivalence_note") for x in d["actives"])
        if got == exp and (has_note == g["salt_note"]):
            out = "CORRECT"
        elif [v for _, v in got] == [v for _, v in exp] or set(got) & set(exp):
            out = "PARTIAL"
        else:
            out = "WRONG"
        add("active_ingredients_strength", out, "; ".join(f"{x['name_raw']} {x['strength_value']} {x['strength_unit']}" for x in d["actives"]),
            "; ".join(f"{n} {v}" for n, v in g["actives"]), "salt/equivalence note expected" if g["salt_note"] else "")

        # strength basis
        add("strength_basis", "CORRECT" if basis_cat(d["per_basis"]) == g["basis"] else "WRONG", d["per_basis"], g["basis"])

        # known-effect excipients (KÜB 2)
        ke_got = sorted(norm(x) for x in d["known_effect_excipients"])
        ke_exp = sorted(norm(x) for x in g["known_effect"])
        ke_out = "CORRECT" if ke_got == ke_exp else ("PARTIAL" if len(set(ke_got) & set(ke_exp)) >= len(ke_exp) - 1 and ke_exp else "WRONG")
        add("known_effect_excipients", ke_out, " | ".join(d["known_effect_excipients"]), " | ".join(g["known_effect"]))

        # form
        f_ok = fold(d["pharmaceutical_form"]).strip(" .") == fold(g["form"])
        f_out = "PARTIAL" if f_ok and g.get("form_ambiguous") else ("CORRECT" if f_ok else "WRONG")
        add("pharmaceutical_form", f_out, d["pharmaceutical_form"], g["form"],
            "KÜB 3 has no form term; description says süspansiyon, name says şurup" if g.get("form_ambiguous") else d.get("form_source", ""))

        # route
        add("route", "CORRECT" if d["routes"] == g["route"] else "WRONG", ";".join(d["routes"]), ";".join(g["route"]), d["route_source"])

        # excipients (KÜB 6.1)
        ex_got = [norm(x) for x in d["excipients"]]
        ex_exp = [norm(x) for x in g["excipients"]]
        if ex_got == ex_exp:
            ex_out = "CORRECT"
        else:
            hit = len(set(ex_got) & set(ex_exp)) / len(ex_exp)
            ex_out = "PARTIAL" if hit >= 0.8 else "WRONG"
        add("excipients", ex_out, " | ".join(d["excipients"]), " | ".join(g["excipients"]),
            f"{len(set(ex_got) & set(ex_exp))}/{len(ex_exp)} items exact")

        # contraindications: section boundary (independent extractor) and item split
        pdf = Path(a.pdf_dir) / f"{sid}_KUB.pdf"
        ref43 = section_by_pdftotext(pdf, "4.3", "4.4")
        b43 = boundary_ok(d["contraindications_text"], ref43) if not ocr else ("PARTIAL" if d["contraindications_text"] else "WRONG")
        add("contraindications_section", b43, f"{len(d['contraindications_text'])} chars", "KÜB 4.3 full text",
            "scanned: OCR text has character errors" if ocr else "boundaries vs pdftotext")
        n = len(d["contraindication_items"])
        add("contraindication_items_split", "CORRECT" if n == g["ci_items"] else "WRONG", n, g["ci_items"])

        # interactions: section boundary
        ref45 = section_by_pdftotext(pdf, "4.5", "4.6")
        b45 = boundary_ok(d["interactions_text"], ref45) if not ocr else ("PARTIAL" if d["interactions_text"] else "WRONG")
        add("interactions_section", b45, f"{d['interactions_chars']} chars", "KÜB 4.5 full text",
            "scanned: OCR text has character errors" if ocr else "boundaries vs pdftotext")

    with open(res_dir / "field_scores.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    fields = list(dict.fromkeys(r["field"] for r in rows))
    summary = []
    for f in fields:
        rs = [r for r in rows if r["field"] == f]
        c = sum(r["outcome"] == "CORRECT" for r in rs)
        p = sum(r["outcome"] == "PARTIAL" for r in rs)
        summary.append({"field": f, "documents": len(rs), "correct": c, "partial": p, "wrong": len(rs) - c - p,
                        "success_rate_pct": round(100 * c / len(rs)), "usable_incl_partial_pct": round(100 * (c + p) / len(rs))})
    with open(res_dir / "summary.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    for s in summary:
        print(f"{s['field']:32} {s['success_rate_pct']:>4}%  (correct {s['correct']}, partial {s['partial']}, wrong {s['wrong']})")
    for r in rows:
        if r["outcome"] != "CORRECT":
            print(f"  {r['sample_id']} {r['field']}: {r['outcome']} | got: {str(r['extracted'])[:110]} | exp: {str(r['expected'])[:80]} {r['note']}")


if __name__ == "__main__":
    main()
