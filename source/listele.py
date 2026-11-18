"""listele.py — TİTCK KÜB/KT listesinin tamamını CSV'ye çeker.
Çalıştırma:  pip install requests   (bir kere)
             python listele.py            -> tüm liste
             python listele.py --test     -> sadece ilk sayfa (deneme)
Çıktı: kubkt_liste.csv
"""
import re, sys, csv, time, json, html
import requests

SITE = "https://www.titck.gov.tr"
SAYFA_BOYU = 100        # her istekte kaç kayıt
BEKLEME = 2             # istekler arası saniye (sunucuyu yormamak için)
SUTUNLAR = ["name", "element", "firmName", "confirmationDateKub",
            "confirmationDateKt", "documentPathKub", "documentPathKt"]

def token_al(oturum):
    """Laravel güvenlik anahtarını bulur. Önce sayfada arar, bulamazsa çerezden alır."""
    from urllib.parse import unquote
    r = oturum.get(f"{SITE}/kubkt", timeout=30)
    r.raise_for_status()
    open("kubkt_sayfa.html", "w", encoding="utf-8").write(r.text)   # sorun olursa incelemek için
    for desen in [r'name="csrf-token"\s+content="([^"]+)"',
                  r'name="_token"\s+value="([^"]+)"',
                  r'_token[^A-Za-z0-9]{1,12}([A-Za-z0-9]{40})',
                  r'csrf[_-]?token[^A-Za-z0-9]{1,12}([A-Za-z0-9]{40})']:
        m = re.search(desen, r.text, re.I)
        if m:
            print("Token sayfada bulundu.")
            return m.group(1)
    xsrf = oturum.cookies.get("XSRF-TOKEN")
    if xsrf:
        print("Token sayfada yok; çerezdeki XSRF-TOKEN kullanılıyor.")
        oturum.headers["X-XSRF-TOKEN"] = unquote(xsrf)
        return ""
    sys.exit(f"Token bulunamadı. Sayfa {len(r.text)} karakter geldi; kubkt_sayfa.html dosyasını gönder.")

def form(start, token, draw):
    veri = {"draw": draw, "start": start, "length": SAYFA_BOYU,
            "search[value]": "", "search[regex]": "false",
            "order[0][column]": 4, "order[0][dir]": "desc"}
    if token:
        veri["_token"] = token
    for i, ad in enumerate(SUTUNLAR):
        veri.update({f"columns[{i}][data]": ad, f"columns[{i}][name]": "",
                     f"columns[{i}][searchable]": "true",
                     f"columns[{i}][orderable]": "true" if i < 5 else "false",
                     f"columns[{i}][search][value]": "", f"columns[{i}][search][regex]": "false"})
    return veri

def pdf_link(deger):
    """Alan düz yol da olabilir, içinde <a href> olan HTML de. İkisini de çözer."""
    if not deger:
        return ""
    s = html.unescape(str(deger))
    m = re.search(r'href=["\']([^"\']+)["\']', s)
    yol = m.group(1) if m else s.strip()
    if yol.startswith("http"):
        return yol
    return f"{SITE}/{yol.lstrip('/')}"

def duz_metin(deger):
    return re.sub(r"<[^>]+>", " ", html.unescape(str(deger or ""))).strip()

def main():
    test = "--test" in sys.argv
    oturum = requests.Session()
    oturum.headers.update({"User-Agent": "PharmAssist-student-project (Yasar Univ.)",
                           "X-Requested-With": "XMLHttpRequest",
                           "Referer": f"{SITE}/kubkt"})
    token = token_al(oturum)
    start, draw, toplam, satirlar = 0, 1, None, []
    while toplam is None or start < toplam:
        r = oturum.post(f"{SITE}/getkubktviewdatatable", data=form(start, token, draw), timeout=60)
        r.raise_for_status()
        cevap = r.json()
        toplam = int(cevap.get("recordsTotal") or cevap.get("recordsFiltered") or 0)
        kayitlar = cevap.get("data", [])
        if draw == 1:
            print("Toplam kayıt:", toplam)
            print("İlk kaydın ham hali (alan adlarını kontrol için):")
            print(json.dumps(kayitlar[0] if kayitlar else {}, ensure_ascii=False, indent=2)[:1500])
        if not kayitlar:
            break
        for k in kayitlar:
            satirlar.append({
                "urun_adi": duz_metin(k.get("name")),
                "etkin_madde": duz_metin(k.get("element")),
                "firma": duz_metin(k.get("firmName")),
                "kub_tarih": duz_metin(k.get("confirmationDateKub")),
                "kt_tarih": duz_metin(k.get("confirmationDateKt")),
                "kub_url": pdf_link(k.get("documentPathKub")),
                "kt_url": pdf_link(k.get("documentPathKt")),
            })
        start += len(kayitlar)
        draw += 1
        print(f"  {start}/{toplam}", end="\r")
        if test:
            break
        time.sleep(BEKLEME)
    with open("kubkt_liste.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(satirlar[0].keys()))
        w.writeheader(); w.writerows(satirlar)
    print(f"\n{len(satirlar)} kayıt kubkt_liste.csv dosyasına yazıldı.")

if __name__ == "__main__":
    main()
