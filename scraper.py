"""Multi-source tender scraper. Reads sources.json + keywords.json, writes data.json."""
import re, json, os, sys, time, datetime, requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # only matters for sources marked insecure

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5"}
TODAY = datetime.date.today()
MONTHS = "Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık"
LINK_RE = re.compile(r"/TR-(\d+)/[^/]+\.html")
DATE_RE = re.compile(rf"(\d{{1,2}}) ({MONTHS}) (\d{{4}})")
DATE_TITLE = re.compile(r"^\d{1,2} \w+ \d{4}$")
LABELS = {"duyurular": "Announcements", "ihale ilanları": "Tenders", "haberler": "News"}
KW = json.load(open("keywords.json", encoding="utf-8"))


_FOLD = str.maketrans("ışğüöçâîû", "isguocaiu")


def norm(s):
    # Turkish-safe lowercase, then fold diacritics so "VÜCUT", "vucut" and "INBODY" all match
    return s.replace("İ", "i").replace("I", "ı").lower().translate(_FOLD)


def score(title, section, files):
    text = norm(title + " " + " ".join(f["name"] for f in files))
    total, matched = KW["section_bonus"].get(section, 0), []
    for cat in KW["categories"].values():
        hits = []
        for t in cat["terms"]:
            n = norm(t)
            end = r"(?!\w)" if len(n) <= 3 else ""  # short terms (bia, bwa, ftr) must be whole words
            if re.search(r"(?<!\w)" + re.escape(n) + end, text):
                hits.append(t)
        if hits:
            total += cat["weight"]
            matched += hits if cat["weight"] > 0 else []
    return max(0, min(100, total)), matched


def get(url, verify=True):
    last = None
    for _ in range(2):  # one retry for flaky connections; HTTP errors (403/404) are not retried
        try:
            r = requests.get(url, timeout=(10, 25), headers=H, verify=verify)
            r.raise_for_status()
            return r.text
        except requests.HTTPError:
            raise
        except requests.RequestException as e:
            last = e
            time.sleep(3)
    raise last


def short_err(e):
    t = str(e)
    if "Caused by" in t:
        t = t.split("Caused by", 1)[1]
    return (type(e).__name__ + ": " + t.strip(" ()"))[:170]


def add(out, a, base, section):
    m = LINK_RE.search(a["href"])
    title = (a.get("title") or a.get_text(" ", strip=True)).strip()
    if m and title and not DATE_TITLE.match(title):
        out.setdefault(urljoin(base, a["href"]), (title, section))


def tab_label(soup, i):
    for t in soup.find_all(True):
        for k in ("href", "data-target", "data-bs-target", "aria-controls"):
            if (t.get(k) or "").lstrip("#") == i and t.get_text(strip=True):
                return LABELS.get(norm(t.get_text(strip=True)), t.get_text(strip=True))
    return "Announcements"


def tr_links(soup, base):
    out = {}
    for box in soup.find_all(id=re.compile(r"^tab(menu)?_?\d+$")):
        sec = tab_label(soup, box["id"])
        for a in box.find_all("a", href=True):
            add(out, a, base, sec)
    if out:
        return out
    allr = {}  # fallback: newest page ids are content, old ids are menu
    for a in soup.find_all("a", href=True):
        add(allr, a, base, "Announcements")
    top = sorted(allr.items(), key=lambda kv: -int(LINK_RE.search(kv[0]).group(1)))[:25]
    return dict(top)


def list_links(soup, base):
    out = {}
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if h.startswith(("#", "javascript", "mailto", "tel")) or a.find_parent(["nav", "header", "footer"]):
            continue
        t = (a.get("title") or a.get_text(" ", strip=True)).strip()
        if len(t) >= 25 and not DATE_TITLE.match(t):
            out.setdefault(urljoin(base, h), (t, "Listing"))
        if len(out) >= 40:
            break
    return out


NMONTHS = [norm(m) for m in MONTHS.split("|")]
DATE_TXT = re.compile(r"(\d{1,2})\s+(" + "|".join(NMONTHS) + r")\s+(20\d{2})")
DATE_NUM = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)")


def parse_dates(t):
    raw = [(m.start(), int(m.group(3)), NMONTHS.index(m.group(2)) + 1, int(m.group(1))) for m in DATE_TXT.finditer(t)]
    raw += [(m.start(), int(m.group(3)), int(m.group(2)), int(m.group(1))) for m in DATE_NUM.finditer(t)]
    good = []
    for pos, y, mo, d in sorted(raw):
        try:
            day = datetime.date(y, mo, d)
        except ValueError:
            continue
        if day <= TODAY:  # future dates are deadlines, not publish dates
            good.append((pos, day))
    return good


def pick_date(text, title):
    """Publish date = first date within 300 chars after the page's own title (ignores menu/widget dates)."""
    t, tt = norm(text), norm(title).strip()
    starts = [m.start() for m in re.finditer(re.escape(tt), t)] if tt else []
    for pos, day in parse_dates(t):
        if any(p <= pos <= p + len(tt) + 300 for p in starts):
            return day.isoformat()
    return None


def detail(link, title=""):
    soup = BeautifulSoup(get(link), "html.parser")
    pub = pick_date(soup.get_text(" ", strip=True), title)
    files = [{"name": a.get_text(strip=True) or a["href"].split("/")[-1], "url": urljoin(link, a["href"])}
             for a in soup.find_all("a", href=True) if "/Eklenti/" in a["href"]]
    return pub, files


def translate(text, tl):
    """Turkish -> en/ko via Google's free web endpoint (unofficial, may be rate limited)."""
    r = requests.get("https://translate.googleapis.com/translate_a/single", headers=H, timeout=8,
                     params={"client": "gtx", "sl": "tr", "tl": tl, "dt": "t", "q": text})
    r.raise_for_status()
    return "".join(seg[0] for seg in r.json()[0] if seg and seg[0]).strip()


def add_translations(rows, limit=100):
    """Fill title_en / title_ko for the highest-scoring untranslated items, max `limit` per run."""
    todo = sorted((i for i in rows if "title_en" not in i or "title_ko" not in i), key=lambda i: -i["score"])[:limit]
    fails = 0
    for it in todo:
        for lang in ("en", "ko"):
            if "title_" + lang in it:
                continue
            try:
                it["title_" + lang] = translate(it["title"], lang)
                time.sleep(0.3)
            except Exception:
                fails += 1
        if fails >= 5:
            print("Translation service not responding, will retry next run.", file=sys.stderr)
            break


def main():
    sources = json.load(open("sources.json", encoding="utf-8"))
    old = json.load(open("data.json", encoding="utf-8")) if os.path.exists("data.json") else {}
    items = {i["link"]: i for i in old.get("items", [])}
    health, budget = [], 150  # max detail pages per run; the rest is picked up next run
    for s in sources:
        try:
            soup = BeautifulSoup(get(s["url"], not s.get("insecure", False)), "html.parser")
            found = tr_links(soup, s["url"]) if s["type"] == "tr" else list_links(soup, s["url"])
            health.append({"name": s["name"], "ok": True, "found": len(found)})
        except Exception as e:
            health.append({"name": s["name"], "ok": False, "error": short_err(e)})
            continue
        for link, (title, section) in found.items():
            if link in items:
                continue
            pub, files, dv = None, [], 0
            if s["type"] == "tr":
                if budget <= 0:
                    continue
                budget -= 1
                try:
                    pub, files = detail(link, title)
                    dv = 2
                except Exception:
                    pass
                time.sleep(1)
            sc, matched = score(title, section, files)
            items[link] = {"title": title, "link": link, "source": s["name"], "category": s["category"],
                           "section": section, "first_seen": TODAY.isoformat(), "published": pub,
                           "files": files, "score": sc, "matched": matched, "date_v": dv}
        time.sleep(1)
    # re-read publish dates of older items (new date rules, version 2); best-scoring first, budget-limited
    tr_names = {s["name"] for s in sources if s["type"] == "tr"}
    for it in sorted(items.values(), key=lambda i: -i["score"]):
        if budget <= 0:
            break
        if it["source"] in tr_names and it.get("date_v") != 2:
            budget -= 1
            try:
                it["published"], files = detail(it["link"], it["title"])
                it["files"] = files or it["files"]
                it["date_v"] = 2
            except Exception:
                pass
            time.sleep(1)
    names = {s["name"] for s in sources}
    items = {l: i for l, i in items.items() if i["source"] in names}  # dropped sources disappear
    for it in items.values():  # re-score everything so keyword edits apply to old items
        it["score"], it["matched"] = score(it["title"], it["section"], it["files"])
    add_translations(list(items.values()))
    rows = sorted(items.values(), key=lambda i: i["published"] or i["first_seen"], reverse=True)[:3000]
    new = {"items": rows, "sources": health}
    if new == {"items": old.get("items"), "sources": old.get("sources")}:
        print("No changes.")
        return
    new["updated"] = datetime.datetime.utcnow().isoformat(timespec="minutes") + "Z"
    json.dump(new, open("data.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{len(rows)} items, {sum(h['ok'] for h in health)}/{len(health)} sources OK")


if __name__ == "__main__":
    main()
