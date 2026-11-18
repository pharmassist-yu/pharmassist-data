import re, csv, json, pathlib, pdfplumber

# KÜB'teki gerçek başlıklar, belgedeki sıralarıyla
SIRA = ["1","2","3","4"] + [f"4.{i}" for i in range(1,10)] + ["5","5.1","5.2","5.3","6"] \
       + [f"6.{i}" for i in range(1,7)] + ["7","8","9","10"]
BASLIK = re.compile(r"^\s*(\d{1,2}(?:\.\d)?)\.?\s+(\S.{2,80})$")
SAYFA_NO = re.compile(r"^\s*\d+\s*(/\s*\d+)?\s*$")          # "4", "15/23"
GEBELIK = re.compile(r"gebelik\s+kategorisi\s*:?\s*([ABCDX])\b", re.I)
ALT_46 = {
    "genel": r"Genel tavsiye",
    "kontrasepsiyon": r"Çocuk doğurma potansiyeli",
    "gebelik": r"Gebelik dönemi",
    "laktasyon": r"Laktasyon dönemi",
    "fertilite": r"Üreme yeteneği",
}

def bolumler(metin):
    parcalar, aktif, idx = {"baslangic": ""}, "baslangic", -1
    for satir in metin.splitlines():
        if SAYFA_NO.match(satir):
            continue                                   # sayfa numaralarını at
        m = BASLIK.match(satir)
        if m and m.group(1) in SIRA:
            yeni = SIRA.index(m.group(1))
            if idx < yeni <= idx + 3:                  # sadece sıradaki başlıkları kabul et
                aktif, idx = m.group(1), yeni
                parcalar[aktif] = ""
                continue
        parcalar[aktif] += satir + "\n"
    return parcalar

def alt_bolumler_46(metin):
    konumlar = sorted((m.start(), ad) for ad, desen in ALT_46.items()
                      for m in [re.search(desen, metin, re.I)] if m)
    sonuc = {}
    for i, (bas, ad) in enumerate(konumlar):
        son = konumlar[i+1][0] if i+1 < len(konumlar) else len(metin)
        sonuc[ad] = metin[bas:son].strip()
    return sonuc

def isle(pdf_yolu):
    with pdfplumber.open(pdf_yolu) as pdf:
        metin = "\n".join((s.extract_text() or "") for s in pdf.pages)
    b = bolumler(metin)
    b46 = b.get("4.6", "")
    g = GEBELIK.search(b46)
    alt = alt_bolumler_46(b46)
    return metin, b, {
        "dosya": pdf_yolu.name,
        "karakter": len(metin),
        "eksik_baslik": ",".join(s for s in ["2","4.3","4.5","4.6","6.1"] if not b.get(s, "").strip()),
        "gebelik_kategorisi": g.group(1).upper() if g else "",
        **{f"4.6_{k}": v for k, v in alt.items()},
    }

if __name__ == "__main__":
    out = pathlib.Path("cikti"); out.mkdir(exist_ok=True)
    satirlar = []
    for pdf in sorted(pathlib.Path("pdfs").glob("*.pdf")):
        metin, b, satir = isle(pdf)
        (out / f"{pdf.stem}.json").write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
        satirlar.append(satir)
        print(f"{pdf.name[:45]:45} | {satir['karakter']:6} kr | gebelik: {satir['gebelik_kategorisi'] or '-'} "
              f"| eksik: {satir['eksik_baslik'] or 'yok'} | 4.6 alt: {[k[4:] for k in satir if k.startswith('4.6_')]}")
    alanlar = sorted({k for s in satirlar for k in s}, key=lambda k: (not k in ("dosya","karakter","eksik_baslik","gebelik_kategorisi"), k))
    with open(out / "ozet.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=alanlar); w.writeheader(); w.writerows(satirlar)
    print("\nAyrıntılar: cikti/*.json  |  Tablo: cikti/ozet.csv")
