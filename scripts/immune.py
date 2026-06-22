#!/usr/bin/env python3
"""Doctor Immune System — turn healed incidents into reusable antibodies.

Commands:
  record-incident --symptom ... --cause ... --fix ... --verify ... [--target ...]
  learn --incident <id-or-path> [--name ...] [--risk low|medium|high]
  match --symptom "..."
  apply-known-fix --symptom "..." [--dry-run]
  list-antibodies

This is intentionally conservative: it proposes or dry-runs fixes. Actual remote
patching should go through openclaw_heal.py / doctor.py with backups + verify.
"""
import argparse, json, os, re, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMMUNE = ROOT / "immune-system"
INCIDENTS = IMMUNE / "incidents"
ANTIBODIES = IMMUNE / "antibodies.json"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def tokenize(s):
    return set(re.findall(r"[a-zA-Z0-9_]+", (s or "").lower()))


def score(symptom, ab):
    rx = ab.get("patternRegex")
    if rx:
        try:
            if re.search(rx, symptom or "", re.I):
                return float(ab.get("confidence", 0.9))
        except re.error:
            pass
    hay = " ".join([ab.get("name", ""), ab.get("diagnosis", ""), ab.get("fixPlan", "")])
    a, b = tokenize(symptom), tokenize(hay)
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 2)


def load_antibodies():
    return load_json(ANTIBODIES, [])


def save_antibodies(items):
    save_json(ANTIBODIES, items)


def cmd_record(a):
    iid = "inc-" + str(uuid.uuid4())[:8]
    obj = {
        "id": iid,
        "ts": now(),
        "target": a.target,
        "platform": a.platform,
        "symptom": a.symptom,
        "evidence": [x for x in (a.evidence or "").split(";;") if x],
        "cause": a.cause,
        "fix": a.fix,
        "verify": [x for x in (a.verify or "").split(";;") if x],
        "risk": a.risk,
        "outcome": a.outcome,
    }
    path = INCIDENTS / f"{iid}.json"
    save_json(path, obj)
    print(json.dumps({"recorded": iid, "path": str(path)}, indent=2))


def load_incident(ref):
    p = Path(ref)
    if p.exists():
        return json.loads(p.read_text())
    p = INCIDENTS / f"{ref}.json"
    if p.exists():
        return json.loads(p.read_text())
    raise SystemExit(f"incident not found: {ref}")


def cmd_learn(a):
    inc = load_incident(a.incident)
    antibodies = load_antibodies()
    aid = "ab-" + re.sub(r"[^a-z0-9]+", "-", (a.name or inc.get("symptom", "incident")).lower()).strip("-")[:48]
    # crude but useful default regex from high-signal words
    words = [w for w in tokenize(inc.get("symptom", "")) if len(w) > 3][:8]
    rx = ".*".join(map(re.escape, words)) if words else re.escape(inc.get("symptom", "")[:60])
    ab = {
        "id": aid,
        "name": a.name or inc.get("symptom", "Known fix"),
        "patternRegex": a.pattern_regex or f"(?i){rx}",
        "diagnosis": inc.get("cause", ""),
        "fixPlan": inc.get("fix", ""),
        "risk": a.risk or inc.get("risk", "medium"),
        "confidence": a.confidence,
        "platform": inc.get("platform", "any"),
        "verifySteps": inc.get("verify", []),
        "rollbackSteps": ["Restore backup created before the fix", "Restart affected service/gateway"],
        "sourceIncident": inc.get("id"),
        "healCount": 1,
        "firstSeen": inc.get("ts", now()),
        "lastSeen": now(),
    }
    # replace same id if exists, else append
    antibodies = [x for x in antibodies if x.get("id") != aid] + [ab]
    save_antibodies(antibodies)
    print(json.dumps({"learned": aid, "antibody": ab}, indent=2, ensure_ascii=False))


def cmd_match(a):
    hits = []
    for ab in load_antibodies():
        s = score(a.symptom, ab)
        if s >= a.threshold:
            hits.append({"score": s, **ab})
    hits.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps({"matches": hits[:10]}, indent=2, ensure_ascii=False))


def cmd_apply(a):
    hits = []
    for ab in load_antibodies():
        s = score(a.symptom, ab)
        if s >= a.threshold:
            hits.append((s, ab))
    hits.sort(key=lambda x: x[0], reverse=True)
    if not hits:
        print(json.dumps({"ok": False, "action": "no_match"}, indent=2)); return
    s, ab = hits[0]
    auto = ab.get("risk") == "low" and s >= 0.85
    result = {
        "matched": ab.get("id"),
        "score": s,
        "risk": ab.get("risk"),
        "autoEligible": auto,
        "dryRun": a.dry_run or not auto,
        "diagnosis": ab.get("diagnosis"),
        "fixPlan": ab.get("fixPlan"),
        "verifySteps": ab.get("verifySteps", []),
        "rollbackSteps": ab.get("rollbackSteps", []),
        "nextAction": "apply via doctor/openclaw_heal with backup + verify" if auto and not a.dry_run else "review/propose only",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_list(a):
    print(json.dumps(load_antibodies(), indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(prog="immune")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record-incident")
    r.add_argument("--symptom", required=True); r.add_argument("--cause", required=True); r.add_argument("--fix", required=True)
    r.add_argument("--verify", default=""); r.add_argument("--evidence", default=""); r.add_argument("--target", default=""); r.add_argument("--platform", default="any")
    r.add_argument("--risk", default="medium", choices=["low", "medium", "high"]); r.add_argument("--outcome", default="healed")
    r.set_defaults(fn=cmd_record)
    l = sub.add_parser("learn"); l.add_argument("--incident", required=True); l.add_argument("--name", default=""); l.add_argument("--pattern-regex", default=""); l.add_argument("--risk", default=""); l.add_argument("--confidence", type=float, default=0.75); l.set_defaults(fn=cmd_learn)
    m = sub.add_parser("match"); m.add_argument("--symptom", required=True); m.add_argument("--threshold", type=float, default=0.35); m.set_defaults(fn=cmd_match)
    a = sub.add_parser("apply-known-fix"); a.add_argument("--symptom", required=True); a.add_argument("--threshold", type=float, default=0.35); a.add_argument("--dry-run", action="store_true"); a.set_defaults(fn=cmd_apply)
    sub.add_parser("list-antibodies").set_defaults(fn=cmd_list)
    args = p.parse_args(); args.fn(args)


if __name__ == "__main__":
    main()
