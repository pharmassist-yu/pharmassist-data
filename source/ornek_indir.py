"""ornek_indir.py — kubkt_liste.csv'den rastgele N KÜB seçip ornek/pdfs/ klasörüne indirir.
Çalıştırma:  python ornek_indir.py        (varsayılan 20 belge)
             python ornek_indir.py 30     (30 belge)
"""
import csv, sys, time, random, pathlib, requests

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
BEKLEME = 2
random.seed(42)                       # aynı örneği tekrar üretebilmek için sabit

satirlar = [r for r in csv.DictReader(open("kubkt_liste.csv", encoding="utf-8-sig")) if r["kub_url"].endswith(".pdf")]
print(f"KÜB linki olan kayıt: {len(satirlar)}")
secilen = random.sample(satirlar, min(N, len(satirlar)))

hedef = pathlib.Path("ornek/pdfs"); hedef.mkdir(parents=True, exist_ok=True)
with open("ornek/secilenler.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(secilen[0].keys())); w.writeheader(); w.writerows(secilen)

oturum = requests.Session()
oturum.headers["User-Agent"] = "PharmAssist-student-project (Yasar Univ.)"
for i, r in enumerate(secilen, 1):
    dosya = hedef / r["kub_url"].split("/")[-1]
    if dosya.exists():
        continue
    try:
        cevap = oturum.get(r["kub_url"], timeout=60)
        if cevap.ok and cevap.content[:4] == b"%PDF":
            dosya.write_bytes(cevap.content)
            print(f"{i:2}/{len(secilen)} ✓ {r['urun_adi'][:50]}")
        else:
            print(f"{i:2}/{len(secilen)} ✗ {r['urun_adi'][:50]} (HTTP {cevap.status_code}, PDF değil)")
    except Exception as e:
        print(f"{i:2}/{len(secilen)} ✗ {r['urun_adi'][:50]} ({e})")
    time.sleep(BEKLEME)
print("Bitti. Belgeler: ornek/pdfs/   Seçilen ürünler: ornek/secilenler.csv")
