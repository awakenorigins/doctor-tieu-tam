#!/usr/bin/env python3
"""Doctor Immune Engine v0.5 — simple outside, safe inside.

Human-facing simple loop:
  record-incident -> learn -> match/apply-known-fix (dry-run first)

Internal safety model:
  incidents/YYYY-MM-DD/*.json
  antibodies/candidate|trusted|deprecated/*.json
  vaccines/fleet_checks/*.json
  generated-tests/*.py

Rules:
  - only learn from verified successful incidents
  - no verified rollback = no auto-heal
  - high risk never auto-heals
  - candidate antibodies propose; trusted low-risk antibodies may be auto-eligible
"""
import argparse, json, os, re, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMMUNE = ROOT / "immune-system"
INCIDENTS = IMMUNE / "incidents"
ANTIBODIES = IMMUNE / "antibodies"
VACCINES = IMMUNE / "vaccines" / "fleet_checks"
TESTS = IMMUNE / "generated-tests"


def now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
def day(): return time.strftime("%Y-%m-%d", time.gmtime())

def load_json(path, default):
    if Path(path).exists(): return json.loads(Path(path).read_text())
    return default

def save_json(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")

def tokenize(s): return set(re.findall(r"[a-zA-Z0-9_]+", (s or "").lower()))

def all_antibody_paths():
    for st in ("candidate", "trusted", "deprecated"):
        yield from (ANTIBODIES / st).glob("*.json")

def load_antibodies(include_deprecated=False):
    items=[]
    for p in all_antibody_paths():
        ab=load_json(p,{})
        if not include_deprecated and ab.get("status") == "deprecated": continue
        ab["_path"] = str(p)
        items.append(ab)
    # compat: import legacy flat antibodies.json if present
    legacy=IMMUNE / "antibodies.json"
    if legacy.exists():
        for ab in load_json(legacy,[]):
            if not any(x.get("id")==ab.get("id") for x in items):
                ab.setdefault("status","candidate"); items.append(ab)
    return items

def antibody_path(ab): return ANTIBODIES / ab.get("status","candidate") / f"{ab['id']}.json"

def normalize_incident(a):
    iid = a.id or ("inc_" + time.strftime("%Y%m%d_") + str(uuid.uuid4())[:8])
    return {
        "incidentId": iid,
        "timestamp": now(),
        "target": {
            "hostAlias": a.host_alias or a.target,
            "target": a.target,
            "os": a.os,
            "openclawVersion": a.openclaw_version,
            "doctorVersion": "0.5.0"
        },
        "symptoms": [x for x in a.symptom.split(";;") if x],
        "evidence": {
            "ports": json.loads(a.ports) if a.ports else {},
            "gateway": a.gateway,
            "healthEndpoint": a.health,
            "redactedLogs": [x for x in a.evidence.split(";;") if x]
        },
        "diagnosis": {"rootCause": a.cause, "confidence": a.diagnosis_confidence},
        "treatment": {
            "actions": [x for x in a.fix.split(";;") if x],
            "risk": a.risk,
            "rollback": a.rollback
        },
        "verify": {"status": a.verify_status, "evidence": [x for x in a.verify.split(";;") if x]},
        "learning": {"shouldCreateAntibody": a.verify_status == "passed", "suggestedAntibodyId": a.suggested_antibody_id},
        "outcome": a.outcome
    }

def cmd_record(a):
    inc = normalize_incident(a)
    path = INCIDENTS / day() / f"{inc['incidentId']}.json"
    save_json(path, inc)
    print(json.dumps({"recorded": inc["incidentId"], "path": str(path)}, indent=2))

def load_incident(ref):
    p=Path(ref)
    if p.exists(): return load_json(p,{})
    for p in INCIDENTS.glob(f"**/{ref}.json"):
        return load_json(p,{})
    raise SystemExit(f"incident not found: {ref}")

def slug(s): return re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-")[:64]

def default_regex(symptoms):
    words=[]
    for s in symptoms:
        words += [w for w in tokenize(s) if len(w)>3]
    return "(?i)" + ".*".join(map(re.escape, words[:8])) if words else "(?i).*"

def cmd_learn(a):
    inc=load_incident(a.incident)
    if inc.get("verify",{}).get("status") != "passed" and not a.force:
        print(json.dumps({"ok":False,"error":"refuse_to_learn_unverified_incident","hint":"use --force only for manual research, not auto-heal"},indent=2)); return
    symptoms=inc.get("symptoms",[])
    aid=a.id or inc.get("learning",{}).get("suggestedAntibodyId") or ("ab_"+slug(symptoms[0] if symptoms else inc.get("incidentId","incident")))
    verify=inc.get("verify",{}).get("evidence",[])
    rollback=inc.get("treatment",{}).get("rollback","")
    risk=a.risk or inc.get("treatment",{}).get("risk","medium")
    status="candidate"
    rollback=[rollback] if rollback else []
    warnings=[]
    if risk=="low" and not rollback:
        warnings.append("low_risk_without_rollback_cannot_auto_heal")
    if not verify:
        warnings.append("no_verify_plan_cannot_auto_heal")
    ab={
        "schemaVersion":"immune.antibody.v1",
        "id":aid,"name":a.name or (symptoms[0] if symptoms else aid),"status":status,
        "diseaseClass":a.disease_class or "unknown",
        "match":{"patternRegex":[a.pattern_regex or default_regex(symptoms)],"requiredSignals":[x for x in a.required_signals.split(',') if x],"negativeSignals":[x for x in a.negative_signals.split(',') if x]},
        "diagnosis":inc.get("diagnosis",{}).get("rootCause",""),
        "fixPlan":{"risk":risk,"requiresApproval": risk != "low","steps":inc.get("treatment",{}).get("actions",[])},
        "verifyPlan":verify,
        "rollbackPlan":rollback,
        "confidence":a.confidence,
        "stats":{"healSuccess":1,"healFail":0,"firstSeen":inc.get("timestamp",now()),"lastSeen":now()},
        "sourceIncident":inc.get("incidentId")
    }
    save_json(antibody_path(ab),ab)
    if warnings:
        print(json.dumps({"warnings":warnings},ensure_ascii=False))
    if a.generate_test:
        TESTS.mkdir(parents=True,exist_ok=True)
        (TESTS / f"test_{aid}.py").write_text(f"# Generated skeleton for {aid}\n# Symptom: {symptoms[:1]}\ndef test_{slug(aid).replace('-','_')}_placeholder():\n    assert True\n")
    print(json.dumps({"learned":aid,"status":status,"path":str(antibody_path(ab))},indent=2))

def component_scores(symptom, ab, evidence=None, env=None):
    evidence=evidence or []; env=env or ""
    patterns=ab.get("match",{}).get("patternRegex",[])
    patternScore=0.0
    for rx in patterns:
        try:
            if re.search(rx,symptom,re.I): patternScore=max(patternScore,1.0)
        except re.error: pass
    if patternScore==0:
        hay=" ".join([ab.get("name",""),ab.get("diagnosis","")])
        a,b=tokenize(symptom),tokenize(hay); patternScore=(len(a&b)/len(a|b)) if a and b else 0
    req=ab.get("match",{}).get("requiredSignals",[])
    neg=ab.get("match",{}).get("negativeSignals",[])
    evtext=" ".join(evidence).lower()
    evidenceScore=1.0 if not req else sum(1 for r in req if r.lower() in evtext)/len(req)
    if any(n.lower() in evtext for n in neg): evidenceScore=0.0
    stats=ab.get("stats",{})
    succ,fail=stats.get("healSuccess",0),stats.get("healFail",0)
    hist=0.5 if succ+fail==0 else max(0,(succ-fail)/(succ+fail))
    envScore=1.0 if not env or env.lower() in str(ab.get("platform","")).lower()+str(ab.get("diseaseClass","")).lower() else 0.5
    total=patternScore*.4+evidenceScore*.3+hist*.2+envScore*.1
    return {"patternScore":round(patternScore,2),"evidenceScore":round(evidenceScore,2),"historicalSuccessScore":round(hist,2),"environmentMatchScore":round(envScore,2),"confidence":round(total,2)}

def rank(symptom,evidence=None,env=None,threshold=.35):
    hits=[]
    for ab in load_antibodies():
        sc=component_scores(symptom,ab,evidence,env)
        if sc["confidence"]>=threshold: hits.append({"score":sc["confidence"],"scores":sc,**ab})
    hits.sort(key=lambda x:x["score"], reverse=True); return hits

def auto_policy(ab, score):
    risk=ab.get("fixPlan",{}).get("risk",ab.get("risk","medium"))
    rollback=ab.get("rollbackPlan",[])
    verify=ab.get("verifyPlan",[])
    status=ab.get("status","candidate")
    if not rollback: return False,"no_verified_rollback"
    if not verify: return False,"no_verify_plan"
    if risk=="high": return False,"high_risk_diagnose_only"
    if risk=="medium": return False,"medium_risk_requires_approval"
    if status!="trusted": return False,"candidate_requires_dry_run_or_human"
    if score<.85: return False,"confidence_below_0.85"
    return True,"auto_safe"

def cmd_match(a):
    print(json.dumps({"matches":rank(a.symptom,a.evidence,a.env,a.threshold)[:10]},indent=2,ensure_ascii=False))

def cmd_apply(a):
    hits=rank(a.symptom,a.evidence,a.env,a.threshold)
    if not hits: print(json.dumps({"ok":False,"action":"no_match"},indent=2)); return
    ab=hits[0]; ok,reason=auto_policy(ab,ab["score"])
    dry=a.dry_run or not ok
    print(json.dumps({"matched":ab["id"],"score":ab["score"],"status":ab.get("status"),"risk":ab.get("fixPlan",{}).get("risk"),"autoEligible":ok,"policyReason":reason,"dryRun":dry,"fixPlan":ab.get("fixPlan"),"verifyPlan":ab.get("verifyPlan"),"rollbackPlan":ab.get("rollbackPlan")},indent=2,ensure_ascii=False))

def cmd_promote(a):
    found=None
    for ab in load_antibodies(include_deprecated=True):
        if ab.get("id")==a.id: found=ab; break
    if not found: raise SystemExit("antibody not found")
    old=Path(found.get("_path")); found.pop("_path",None)
    stats=found.setdefault("stats",{})
    succ,fail=stats.get("healSuccess",0),stats.get("healFail",0)
    if a.status=="trusted" and succ<3 and not a.force:
        print(json.dumps({"ok":False,"error":"needs_3_successes_or_force"},indent=2)); return
    found["status"]=a.status
    if old.exists(): old.unlink()
    save_json(antibody_path(found),found)
    print(json.dumps({"promoted":a.id,"status":a.status},indent=2))

def cmd_vaccine(a):
    ab=next((x for x in load_antibodies() if x.get("id")==a.antibody),None)
    if not ab: raise SystemExit("antibody not found")
    fleet=load_json(Path(a.fleet),[])
    out=[]
    for host in fleet:
        out.append({"host":host.get("name") or host.get("target"),"target":host.get("target"),"antibody":ab["id"],"action":"dry-run-scan","checks":ab.get("match",{}).get("requiredSignals",[])})
    print(json.dumps({"dryRun":True,"items":out},indent=2))

REQUIRED_AB_FIELDS = ("id", "name", "status", "match", "fixPlan")


def cmd_validate(a):
    problems=[]
    for ab in load_antibodies(include_deprecated=True):
        path=ab.get("_path","?")
        for f in REQUIRED_AB_FIELDS:
            if f not in ab: problems.append({"path":path,"missing":f})
        if ab.get("status") not in ("candidate","trusted","deprecated"):
            problems.append({"path":path,"bad_status":ab.get("status")})
        if ab.get("schemaVersion") != "immune.antibody.v1":
            problems.append({"path":path,"warn":"missing_or_old_schemaVersion"})
        rx=ab.get("match",{}).get("patternRegex",[])
        for r in rx:
            try: re.compile(r)
            except re.error as e: problems.append({"path":path,"bad_regex":r,"err":str(e)})
    print(json.dumps({"ok":len(problems)==0,"problems":problems},indent=2,ensure_ascii=False))


def cmd_list(a): print(json.dumps(load_antibodies(include_deprecated=True),indent=2,ensure_ascii=False))

def main():
    p=argparse.ArgumentParser(prog="immune"); sub=p.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("record-incident");
    for x in ["symptom","cause","fix"]: r.add_argument(f"--{x}",required=True)
    r.add_argument("--id",default=""); r.add_argument("--target",default=""); r.add_argument("--host-alias",default=""); r.add_argument("--os",default="any"); r.add_argument("--openclaw-version",default=""); r.add_argument("--ports",default=""); r.add_argument("--gateway",default=""); r.add_argument("--health",default=""); r.add_argument("--evidence",default=""); r.add_argument("--diagnosis-confidence",type=float,default=.8); r.add_argument("--risk",default="medium",choices=["low","medium","high"]); r.add_argument("--rollback",default=""); r.add_argument("--verify",default=""); r.add_argument("--verify-status",default="passed",choices=["passed","failed","unknown"]); r.add_argument("--suggested-antibody-id",default=""); r.add_argument("--outcome",default="healed"); r.set_defaults(fn=cmd_record)
    l=sub.add_parser("learn"); l.add_argument("--incident",required=True); l.add_argument("--id",default=""); l.add_argument("--name",default=""); l.add_argument("--disease-class",default=""); l.add_argument("--pattern-regex",default=""); l.add_argument("--required-signals",default=""); l.add_argument("--negative-signals",default=""); l.add_argument("--risk",default=""); l.add_argument("--confidence",type=float,default=.72); l.add_argument("--generate-test",action="store_true"); l.add_argument("--force",action="store_true"); l.set_defaults(fn=cmd_learn)
    m=sub.add_parser("match"); m.add_argument("--symptom",required=True); m.add_argument("--evidence",action="append",default=[]); m.add_argument("--env",default=""); m.add_argument("--threshold",type=float,default=.35); m.set_defaults(fn=cmd_match)
    a=sub.add_parser("apply-known-fix"); a.add_argument("--symptom",required=True); a.add_argument("--evidence",action="append",default=[]); a.add_argument("--env",default=""); a.add_argument("--threshold",type=float,default=.35); a.add_argument("--dry-run",action="store_true"); a.set_defaults(fn=cmd_apply)
    pr=sub.add_parser("antibodies-promote"); pr.add_argument("--id",required=True); pr.add_argument("--status",required=True,choices=["candidate","trusted","deprecated"]); pr.add_argument("--force",action="store_true"); pr.set_defaults(fn=cmd_promote)
    v=sub.add_parser("vaccinate-fleet"); v.add_argument("--fleet",required=True); v.add_argument("--antibody",required=True); v.add_argument("--dry-run",action="store_true"); v.set_defaults(fn=cmd_vaccine)
    sub.add_parser("list-antibodies").set_defaults(fn=cmd_list)
    sub.add_parser("validate-antibodies").set_defaults(fn=cmd_validate)
    args=p.parse_args(); args.fn(args)
if __name__=="__main__": main()
