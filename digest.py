"""Daily digest: writes digest.md with NEW, relevant tenders not yet reported. Writes nothing when there are none.
Run by .github/workflows/digest.yml, which turns digest.md into a GitHub issue (GitHub then e-mails the watchers)."""
import datetime
import json
import os

MIN_SCORE = 70          # only strong product matches are worth an e-mail
MAX_AGE_DAYS = 30       # older items are archived, never reported
SITE = "https://ardacaniren.github.io/ihaletakip/"


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


data = load("data.json", {"items": []})
sent = load("digest_sent.json", {"links": []})
sent_links = set(sent.get("links", []))
dismissed = set((load("dismissed.json", {}).get("items") or {}).keys())
cut = (datetime.date.today() - datetime.timedelta(days=MAX_AGE_DAYS)).isoformat()

new = [i for i in data["items"]
       if i["score"] >= MIN_SCORE and i["link"] not in sent_links and i["link"] not in dismissed
       and (i.get("published") or i["first_seen"]) >= cut]
new.sort(key=lambda i: -i["score"])
for f in ("digest.md", "digest_title.txt"):
    if os.path.exists(f):
        os.remove(f)
if new:
    day = datetime.date.today().strftime("%d.%m.%Y")
    lines = [f"{len(new)} new relevant tender notice(s) scoring {MIN_SCORE}+. Dashboard: {SITE}", ""]
    for i in new:
        pub = f", published {i['published']}" if i.get("published") else ""
        title = i.get("title_en") or i["title"]
        lines.append(f"- **{i['score']}** [{title}]({i['link']}) ({i['source']}{pub})")
        if i.get("title_en") and i["title_en"] != i["title"]:
            lines.append(f"  - Turkish original: {i['title']}")
        if i.get("matched"):
            lines.append(f"  - matched: {', '.join(i['matched'][:8])}")
    open("digest.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    open("digest_title.txt", "w", encoding="utf-8").write(f"InBody tender digest {day}: {len(new)} new relevant notice(s)")
    sent["links"] = sorted(sent_links | {i["link"] for i in new})
    json.dump(sent, open("digest_sent.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{len(new)} item(s) to report")
