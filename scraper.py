"""Konya İl Sağlık Müdürlüğü takip scraper'ı.
Çalıştırma: python scraper.py  ->  data.json üretir/günceller.
"""
import re, json, os, sys, time, datetime
import requests
from bs4 import BeautifulSoup

BASE = "https://konyaism.saglik.gov.tr"
DATA = "data.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Sayfadaki bölümlerin HTML id'leri (sayfa görünümünden alındı, gerekirse düzeltin)
SECTIONS = {
    "Duyurular": "tabmenu56237",
    "İhale İlanları": "tabmenu56464",
    "Haberler": "tab_55643",
}

# Anahtar kelime -> puan (Satış ekibinin sözlüğüyle değiştirilecek)
KEYWORDS = {
    "vücut kompozisyon": 60, "vücut sıvı": 60, "bia": 40, "analizör": 30,
    "diyaliz": 25, "nefroloji": 20, "obezite": 25, "beslenme": 15, "diyet": 15,
    "sporcu sağlığı": 20, "ftr": 10, "kronik hastalık": 15, "sağlıklı yaşam": 10,
    "tıbbi cihaz": 30, "satın al": 20, "şartname": 20, "ihale": 15, "alım": 10,
}
SECTION_BONUS = {"İhale İlanları": 20}
MONTHS = "Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık"
LINK_RE = re.compile(r"/TR-(\d+)/.+\.html")


def norm(s):
    # Türkçe İ/I sorununu önlemek için önce elle çevir
    return s.replace("İ", "i").replace("I", "ı").lower()


def score(title, section, files):
    text = norm(title + " " + " ".join(f["name"] for f in files))
    total = SECTION_BONUS.get(section, 0)
    for kw, pts in KEYWORDS.items():
        if re.search(r"(?<!\w)" + re.escape(norm(kw)), text):
            total += pts
    return min(total, 100)


def get(url):
    r = requests.get(url, timeout=20, headers=HEADERS)
    r.raise_for_status()
    return r.text


def list_items(html):
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for section, el_id in SECTIONS.items():
        box = soup.find(id=el_id)
        if not box:
            print(f"UYARI: '{el_id}' bulunamadı ({section})", file=sys.stderr)
            continue
        for a in box.find_all("a", href=True):
            if LINK_RE.search(a["href"]):
                link = a["href"] if a["href"].startswith("http") else BASE + a["href"]
                title = (a.get("title") or a.get_text(strip=True)).strip()
                if title:
                    found.setdefault(link, (title, section))
    return found


def detail(link):
    soup = BeautifulSoup(get(link), "html.parser")
    text = soup.get_text(" ", strip=True)
    m = re.search(rf"(\d{{1,2}}) ({MONTHS}) (\d{{4}})", text)
    published = None
    if m:
        month = MONTHS.split("|").index(m.group(2)) + 1
        published = f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}"
    files = [{"name": a.get_text(strip=True) or a["href"].split("/")[-1], "url": a["href"]}
             for a in soup.find_all("a", href=True) if "/Eklenti/" in a["href"]]
    return published, files


def main():
    old = json.load(open(DATA, encoding="utf-8")) if os.path.exists(DATA) else {"items": []}
    items = {i["link"]: i for i in old["items"]}
    today = datetime.date.today().isoformat()

    found = list_items(get(BASE + "/"))
    if not found:
        sys.exit("HATA: hiç ilan bulunamadı (site yapısı değişmiş veya erişim engellenmiş olabilir)")

    new = [(l, t, s) for l, (t, s) in found.items() if l not in items][:40]
    for link, title, section in new:
        try:
            published, files = detail(link)
        except Exception as e:
            print("Detay alınamadı:", link, e, file=sys.stderr)
            published, files = None, []
        items[link] = {"title": title, "link": link, "section": section,
                       "first_seen": today, "published": published, "files": files,
                       "score": score(title, section, files)}
        time.sleep(1.5)  # siteye nazik davran

    if not new and os.path.exists(DATA):
        print("Yeni içerik yok.")
        return
    ordered = sorted(items.values(), key=lambda i: (i["published"] or i["first_seen"]), reverse=True)
    json.dump({"updated": datetime.datetime.now().isoformat(timespec="minutes"), "items": ordered},
              open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(new)} yeni kayıt eklendi, toplam {len(ordered)}.")


if __name__ == "__main__":
    main()
