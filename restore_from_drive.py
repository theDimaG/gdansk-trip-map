#!/usr/bin/env python3
"""Restore the shared trip plan from a backup file written by backup_to_drive.py.

Usage:  python3 restore_from_drive.py "<Drive>/Claude/gdansk-trip/backups/plan-20260927-1200.json"
Shows what will be restored and asks for confirmation before writing to Firestore.
The planner page picks the change up live (last write wins).
"""
import json
import sys
import urllib.request

PROJECT = "gdansk-trip-441f9"
DOC = "trips/gdansk-2026"
API_KEY = "AIzaSyDSiZ2iBLXrmH6Rj6XF-ZYTGN1dCf_StXA"


def encode(v):
    """plain Python -> Firestore REST value."""
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, list):
        return {"arrayValue": {"values": [encode(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: encode(x) for k, x in v.items()}}}
    return {"stringValue": str(v)}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    plan = data["plan"]
    days = plan.get("days", []) or []
    print("backup from:", data.get("exported"))
    print("days: %d, stops: %d, custom places: %d" % (len(days), sum(len(d.get("stops") or []) for d in days), len(plan.get("custom") or [])))
    for i, d in enumerate(days):
        print("  day %d: %s (%d stops)" % (i + 1, d.get("title") or "-", len(d.get("stops") or [])))
    if input("Restore this plan to the live planner? It replaces the current plan. [yes/N] ").strip().lower() != "yes":
        print("cancelled")
        return
    url = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/%s?key=%s" % (PROJECT, DOC, API_KEY)
    body = json.dumps({"fields": {k: encode(v) for k, v in plan.items()}}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="PATCH", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
    print("restored")


if __name__ == "__main__":
    main()
