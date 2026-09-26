#!/usr/bin/env python3
"""Back up the shared trip plan (Firestore) to the synced Google Drive folder.

Runs on the Mac every hour via launchd (com.gomazov.gdansk-trip-backup).
Writes, under <Drive>/Claude/gdansk-trip/:
  backups/plan-YYYYMMDD-HHMM.json   a new snapshot only when the plan changed
  plan-latest.json                  always the newest copy
  מסלול.md                          a readable version of the itinerary
Python 3.9 compatible (the launchd job uses Apple's python3.9, which has Drive access).
"""
import datetime
import hashlib
import json
import os
import sys
import urllib.request

PROJECT = "gdansk-trip-441f9"
DOC = "trips/gdansk-2026"
API_KEY = "AIzaSyDSiZ2iBLXrmH6Rj6XF-ZYTGN1dCf_StXA"  # public Firebase web key; access is governed by Firestore rules
DRIVE = "/Users/gomazov/Library/CloudStorage/GoogleDrive-gomazov@gmail.com/האחסון שלי/Claude/gdansk-trip"
PLACES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "maps-dashboard", "lists.json")
KEEP = 60
HE_DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]


def decode(v):
    """Firestore REST value -> plain Python."""
    if "stringValue" in v:
        return v["stringValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    if "booleanValue" in v:
        return v["booleanValue"]
    if "nullValue" in v:
        return None
    if "mapValue" in v:
        return {k: decode(x) for k, x in (v["mapValue"].get("fields") or {}).items()}
    if "arrayValue" in v:
        return [decode(x) for x in (v["arrayValue"].get("values") or [])]
    if "timestampValue" in v:
        return v["timestampValue"]
    return v


def fetch_plan():
    url = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/%s?key=%s" % (PROJECT, DOC, API_KEY)
    with urllib.request.urlopen(url, timeout=30) as r:
        raw = json.load(r)
    return {k: decode(v) for k, v in raw.get("fields", {}).items()}


def load_places():
    places = {}
    try:
        data = json.load(open(PLACES, encoding="utf-8"))
        for lid, lst in data.items():
            for it in lst["items"]:
                cid = it.get("cid")
                if cid:
                    n = int(cid)
                    if n < 0:
                        n += 2 ** 64
                    pid = str(n)
                else:
                    pid = "%s,%s" % (it["lat"], it["lng"])
                places[pid] = {"name": it["name"], "note": it.get("note", ""), "lat": it["lat"], "lng": it["lng"], "list": lst["title"]}
    except Exception as e:  # the plan is still backed up without names
        print("places lookup unavailable:", e)
    return places


def day_date(start, i):
    if not start:
        return None
    try:
        d = datetime.date.fromisoformat(start)
    except ValueError:
        return None
    return d + datetime.timedelta(days=i)


def to_markdown(plan, places):
    s = plan.get("settings", {}) or {}
    lines = ["# מסלול הטיול לגדנסק", ""]
    lines.append("גיבוי מ-%s" % datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))
    if s.get("start"):
        lines.append("הגעה: %s · %s לילות" % (s["start"], s.get("nights", "")))
    if s.get("hotel"):
        h = s["hotel"]
        lines.append("לינה: %s (%.5f, %.5f)" % (h.get("name", ""), h.get("lat", 0), h.get("lng", 0)))
    lines.append("התניידות: %s" % {"DRIVING": "רכב", "WALKING": "הליכה", "TRANSIT": "תחבורה ציבורית"}.get(s.get("mode"), s.get("mode", "")))
    lines.append("")
    for i, d in enumerate(plan.get("days", []) or []):
        date = day_date(s.get("start"), i)
        head = "יום %s %d.%d" % (HE_DAYS[(date.weekday() + 1) % 7], date.day, date.month) if date else "יום %d" % (i + 1)
        if d.get("title"):
            head += " · " + d["title"]
        lines.append("## " + head)
        if d.get("note"):
            lines.append("_%s_" % d["note"])
        stops = d.get("stops") or []
        if not stops:
            lines.append("(ריק)")
        for j, st in enumerate(stops):
            p = places.get(str(st.get("pid")), {})
            name = p.get("name") or st.get("pid")
            line = "%d. **%s**" % (j + 1, name)
            if p.get("lat") is not None:
                line += " — https://www.google.com/maps/search/?api=1&query=%s,%s" % (p["lat"], p["lng"])
            lines.append(line)
            if p.get("note"):
                lines.append("   - %s" % p["note"])
            if st.get("note"):
                lines.append("   - הערת תכנון: %s" % st["note"])
        lines.append("")
    if plan.get("custom"):
        lines.append("## מקומות שנוספו מגוגל מפות")
        for c in plan["custom"]:
            lines.append("- **%s** (%s) — %s" % (c.get("name"), c.get("area", ""), c.get("uri") or "https://www.google.com/maps/search/?api=1&query=%s,%s" % (c.get("lat"), c.get("lng"))))
        lines.append("")
    packing = plan.get("packing") or []
    if packing:
        done = sum(1 for x in packing if x.get("done"))
        lines.append("## רשימת ציוד (%d/%d נלקחו)" % (done, len(packing)))
        cats = []
        for x in packing:
            c = x.get("cat") or "אחר"
            if c not in cats:
                cats.append(c)
        for c in cats:
            lines.append("### " + c)
            for x in packing:
                if (x.get("cat") or "אחר") == c:
                    lines.append("- [%s] %s" % ("x" if x.get("done") else " ", x.get("text", "")))
            lines.append("")
    return "\n".join(lines)


def main():
    plan = fetch_plan()
    places = load_places()
    for c in plan.get("custom", []) or []:
        places[str(c.get("id"))] = {"name": c.get("name"), "note": c.get("note", ""), "lat": c.get("lat"), "lng": c.get("lng"), "list": "נוסף מגוגל מפות"}

    os.makedirs(os.path.join(DRIVE, "backups"), exist_ok=True)
    body = json.dumps({"exported": datetime.datetime.now().isoformat(timespec="seconds"), "doc": DOC, "plan": plan,
                       "places": {pid: places[pid] for d in plan.get("days", []) or [] for st in (d.get("stops") or []) for pid in [str(st.get("pid"))] if pid in places}},
                      ensure_ascii=False, indent=1)
    digest = hashlib.sha1(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    latest = os.path.join(DRIVE, "plan-latest.json")
    prev_digest = None
    if os.path.exists(latest):
        try:
            prev_digest = hashlib.sha1(json.dumps(json.load(open(latest, encoding="utf-8"))["plan"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        except Exception:
            prev_digest = None

    if digest == prev_digest:
        print("no change since last backup")
        return
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    snap = os.path.join(DRIVE, "backups", "plan-%s.json" % stamp)
    with open(snap, "w", encoding="utf-8") as f:
        f.write(body)
    with open(latest, "w", encoding="utf-8") as f:
        f.write(body)
    with open(os.path.join(DRIVE, "מסלול.md"), "w", encoding="utf-8") as f:
        f.write(to_markdown(plan, places))
    snaps = sorted(x for x in os.listdir(os.path.join(DRIVE, "backups")) if x.startswith("plan-") and x.endswith(".json"))
    for old in snaps[:-KEEP]:
        os.remove(os.path.join(DRIVE, "backups", old))
    n_stops = sum(len(d.get("stops") or []) for d in plan.get("days", []) or [])
    print("backed up: %s (%d days, %d stops)" % (snap, len(plan.get("days", []) or []), n_stops))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("backup failed:", e)
        sys.exit(1)
