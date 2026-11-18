"""ayir3.py — ayir2.py'nin ürettiği cikti/*.json dosyalarından yapılandırılmış alanlar çıkarır.
Çalıştırma:  python ayir3.py      Çıktı: cikti/alanlar.csv ve cikti/alanlar.json
"""
import re, csv, json, pathlib
from ayir2 import alt_bolumler_46, GEBELIK

BIRIM = r"(mg|g|mcg|µg|μg|IU|IE|ml|mL|%)"
SAYI = r"(\d+(?:[.,]\d+)?)"

def temizle(s):
    s = re.sub(r"\([^)]*\)", "", s)          # parantez içini at: "(459,17 mg ... olarak)"
    s = s.replace("*", "").replace("…", ".")
    return re.sub(r"\s+", " ", s).strip(" .:;")

# ---------- 1) Bölüm 2: etkin maddeler ve miktarları ----------
def etkin_maddeler(b2):
    m = re.search(r"Etkin madde(?:\(ler\)|ler)?\s*:?(.*?)(?:Yardımcı madde|$)", b2, re.S | re.I)
    if not m:
        return [], ""
    hacim, sonuc = "", []
    for satir in m.group(1).splitlines():
        t = temizle(satir)
        if not t:
            continue
        h = re.match(r"^Her\s+(.+?)['’]?(?:de|da|te|ta)\s*$", t, re.I)   # "Her 5 ml’de:"
        if h:
            hacim = h.group(1); continue
        a = re.match(rf"^(.+?)[\s.]*\s{SAYI}\s*{BIRIM}$", t)              # "Varfarin sodyum.... 10 mg"
        b = re.match(rf"^{SAYI}\s*{BIRIM}\s+(.+)$", t)                     # "500 mg parasetamol"
        if a:
            sonuc.append({"madde": a.group(1).strip(" ."), "miktar": a.group(2), "birim": a.group(3)})
        elif b:
            sonuc.append({"madde": b.group(3).strip(" ."), "miktar": b.group(1), "birim": b.group(2)})
    return sonuc, hacim

# ---------- 2) Bölüm 6.1: yardımcı maddeler ----------
def yardimci_maddeler(b61):
    ogeler = []
    for satir in b61.splitlines():
        s = satir.strip(" -•\t")
        if not s:
            continue
        if ogeler and (s[0].islower() or ogeler[-1].endswith((",", "("))):
            ogeler[-1] += " " + s                 # alt satıra taşmış öğeyi birleştir
        else:
            ogeler.append(s)
    return [{"madde": temizle(o), "not": "; ".join(re.findall(r"\(([^)]*)\)", o))} for o in ogeler]

# ---------- 3) Gebelik / laktasyon: anahtar kelimeyle sınıflama ----------
KURALLAR = [   # sıra önemli: ilk eşleşen kazanır
    ("kontrendike", r"kontrendike|kullanılmamalıdır|kullanılmamalı|emzirme\w* (?:kesilmeli|durdurulmalı)"),
    ("dikkatli",    r"dikkatli|dikkatle|fayda\s*/\s*risk|yarar\s*/\s*risk|kesilmesi gerekebilir|izlenmelidir"),
    ("guvenli",     r"risk oluşturmaz|güvenle kullanılabilir|güvenlidir"),
]
def sinifla(metin):
    for sinif, desen in KURALLAR:
        m = re.search(desen, metin, re.I)
        if m:
            bas = max(0, m.start() - 60)
            return sinif, "…" + metin[bas:m.end() + 40].replace("\n", " ") + "…"
    return "belirsiz", ""

def isle(json_yolu):
    b = json.loads(json_yolu.read_text(encoding="utf-8"))
    em, hacim = etkin_maddeler(b.get("2", ""))
    ym = yardimci_maddeler(b.get("6.1", ""))
    alt = alt_bolumler_46(b.get("4.6", ""))
    g = GEBELIK.search(b.get("4.6", ""))
    atc = re.search(r"ATC\s*kodu\s*:?\s*([A-Z]\d{2}[A-Z]{2}\d{2})", b.get("5.1", ""), re.I)
    geb_sinif, geb_kanit = sinifla(alt.get("gebelik", ""))
    lak_sinif, lak_kanit = sinifla(alt.get("laktasyon", ""))
    return {
        "dosya": json_yolu.stem,
        "urun_adi": b.get("1", "").strip(),
        "atc": atc.group(1) if atc else "",
        "etkin_maddeler": em,
        "birim_hacim": hacim,
        "yardimci_maddeler": ym,
        "gebelik_kategorisi": g.group(1).upper() if g else "",
        "gebelik_sinif": geb_sinif, "gebelik_kanit": geb_kanit,
        "laktasyon_sinif": lak_sinif, "laktasyon_kanit": lak_kanit,
    }

if __name__ == "__main__":
    kayitlar = [isle(p) for p in sorted(pathlib.Path("cikti").glob("*.json")) if p.name != "alanlar.json"]
    pathlib.Path("cikti/alanlar.json").write_text(json.dumps(kayitlar, ensure_ascii=False, indent=2), encoding="utf-8")
    with open("cikti/alanlar.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["dosya", "urun_adi", "atc", "etkin_maddeler", "yardimci_maddeler",
                    "gebelik_kategorisi", "gebelik_sinif", "gebelik_kanit", "laktasyon_sinif", "laktasyon_kanit"])
        for k in kayitlar:
            em = "; ".join(f"{e['madde']} {e['miktar']} {e['birim']}" for e in k["etkin_maddeler"])
            if k["birim_hacim"]:
                em += f" (her {k['birim_hacim']})"
            w.writerow([k["dosya"], k["urun_adi"], k["atc"], em,
                        "; ".join(y["madde"] for y in k["yardimci_maddeler"]),
                        k["gebelik_kategorisi"], k["gebelik_sinif"], k["gebelik_kanit"],
                        k["laktasyon_sinif"], k["laktasyon_kanit"]])
    for k in kayitlar:
        print("=" * 70)
        print(k["urun_adi"], "| ATC:", k["atc"] or "-")
        print("  Etkin:", "; ".join(f"{e['madde']} {e['miktar']} {e['birim']}" for e in k["etkin_maddeler"]) or "BULUNAMADI",
              f"(her {k['birim_hacim']})" if k["birim_hacim"] else "")
        print("  Yardımcı:", "; ".join(y["madde"] + (f" [{y['not']}]" if y["not"] else "") for y in k["yardimci_maddeler"]))
        print("  Gebelik:", k["gebelik_kategorisi"], "→", k["gebelik_sinif"], "|", k["gebelik_kanit"])
        print("  Laktasyon:", k["laktasyon_sinif"], "|", k["laktasyon_kanit"])
    print("\nTablo: cikti/alanlar.csv  |  Ayrıntı: cikti/alanlar.json")
