#!/usr/bin/env python3
"""Doctor Tiểu Tâm — remote heal CLI for PCs and other OpenClaw instances.

Subcommands:
  connect-test --target user@host [--key PATH]
  scan         --target user@host [--key PATH]
  health       --target user@host [--key PATH]
  check        "<symptom>"
  log          --symptom .. --cause .. --fix .. --fix-type retry|patch|heal --target ..
  list-fixes

Safety: never logs in without an operator-provided key; never prints secrets.
"""
import argparse, base64, json, os, re, subprocess, sys, time, uuid, shlex
from pathlib import Path


def ps_encoded(ps_script):
    """Wrap a PowerShell script as -EncodedCommand to avoid SSH/shell quoting issues."""
    enc = base64.b64encode(ps_script.encode("utf-16-le")).decode()
    return "powershell -NoProfile -EncodedCommand " + enc

WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
KNOWN_FIXES = WORKSPACE / "known-fixes.json"
DEFAULT_KEY = str(Path.home() / ".ssh" / "doctor_tt")


def ssh_base(target, key):
    k = key or DEFAULT_KEY
    return [
        "ssh", "-i", k,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=15",
        "-o", "BatchMode=yes",
        target,
    ]


def run_remote(target, key, remote_cmd, timeout=40):
    cmd = ssh_base(target, key) + [remote_cmd]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # noqa
        return 1, "", str(e)


def detect_os(target, key):
    """Return one of: linux, darwin, windows, unreachable, auth_failed, timeout, unknown.
    Never blindly assume windows on failure (audit fix).
    """
    rc, out, err = run_remote(target, key, "uname -s 2>/dev/null || echo __WINPROBE__")
    low = (err or "").lower()
    if rc == 124 or "timeout" in low:
        return "timeout"
    o = (out or "").strip()
    # Windows OpenSSH often runs under cmd.exe: `uname` fails but the fallback marker
    # may still appear with a non-zero rc/stderr. Treat marker as a probe signal.
    if "__WINPROBE__" in o:
        rc2, out2, _ = run_remote(target, key, "echo %OS%")
        if rc2 == 0 and "Windows" in (out2 or ""):
            return "windows"
        rc3, out3, _ = run_remote(target, key, "ver")
        if rc3 == 0 and "Windows" in (out3 or ""):
            return "windows"
        return "unknown"
    if rc != 0:
        if "permission denied" in low or "publickey" in low or "authentication" in low:
            return "auth_failed"
        if "could not resolve" in low or "connection refused" in low or "no route" in low or "unreachable" in low:
            return "unreachable"
        return "unknown"
    if not o:
        return "unknown"
    return o.lower()  # linux / darwin


GATEWAY_PORTS = (18789, 20128, 20131)


def cmd_verify(a):
    """Prove the patient is healthy with real evidence (audit fix: verify was documented but missing)."""
    osname = detect_os(a.target, a.key)
    ev = {"target": a.target, "os": osname, "ts": int(time.time()), "checks": [], "ok": False}
    if osname in ("unreachable", "auth_failed", "timeout", "unknown"):
        ev["error"] = f"cannot verify: host {osname}"
        print(json.dumps(ev, indent=2)); return
    if osname == "windows":
        ps = ("$r=@();"
              "$t=(Get-ScheduledTask -TaskName 'OpenClaw Gateway' -EA SilentlyContinue).State;"
              "$r+='GATEWAY_TASK='+$t;"
              "foreach($p in 18789,20128,20131){$l=Get-NetTCPConnection -State Listen -LocalPort $p -EA SilentlyContinue; if($l){$r+='PORT_'+$p+'=listen'}};"
              "try{$h=Invoke-WebRequest -Uri http://127.0.0.1:20131/health -TimeoutSec 5 -UseBasicParsing; $r+='PROXY_HEALTH='+$h.StatusCode}catch{$r+='PROXY_HEALTH=fail'};"
              "$r -join [Environment]::NewLine")
        rc, out, err = run_remote(a.target, a.key, ps_encoded(ps))
    else:
        sh = ("echo GATEWAY=$(systemctl is-active openclaw-gateway 2>/dev/null || (pgrep -f openclaw >/dev/null && echo running || echo unknown));"
              "for p in 18789 20128 20131; do ss -ltn 2>/dev/null | grep -q \":$p\" && echo PORT_$p=listen; done;"
              "echo PROXY_HEALTH=$(curl -fsS -m5 http://127.0.0.1:20131/health >/dev/null 2>&1 && echo 200 || echo fail)")
        rc, out, err = run_remote(a.target, a.key, sh)
    raw = out or err
    ev["checks"] = [l for l in raw.splitlines() if l.strip()]
    ev["ok"] = ("GATEWAY_TASK=Running" in raw) or ("GATEWAY=running" in raw) or any("PORT_18789=listen" in c for c in ev["checks"])
    print(json.dumps(ev, indent=2))


def cmd_connect_test(a):
    rc, out, err = run_remote(a.target, a.key, "echo DOCTOR_OK")
    if rc == 0 and "DOCTOR_OK" in out:
        print(json.dumps({"ok": True, "target": a.target, "os": detect_os(a.target, a.key)}))
    else:
        print(json.dumps({"ok": False, "target": a.target, "rc": rc, "err": err or out}))


def cmd_scan(a):
    osname = detect_os(a.target, a.key)
    result = {"target": a.target, "os": osname, "ts": int(time.time()), "findings": {}}
    if osname == "windows":
        ps = ("$ErrorActionPreference='SilentlyContinue';"
              "$t=Get-ScheduledTask | ?{$_.TaskName -like '*OpenClaw*'} | %{$_.TaskName+'='+($_.State)};"
              "$ports=(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ?{$_.LocalPort -in 18789,20128,20131} | %{$_.LocalPort} | Sort-Object -Unique) -join ',';"
              "Write-Output ('TASKS:'+($t -join ';'));"
              "Write-Output ('PORTS:'+$ports)")
        rc, out, err = run_remote(a.target, a.key, ps_encoded(ps))
        result["findings"]["raw"] = out or err
    else:
        sh = ("echo OS:$(uname -a);"
              "echo GATEWAY:$(systemctl is-active openclaw-gateway 2>/dev/null || pgrep -f openclaw >/dev/null && echo running || echo unknown);"
              "echo PORTS:$(ss -ltn 2>/dev/null | grep -oE ':(18789|20128|20131)' | tr '\\n' ',');"
              "echo DISK:$(df -h / | tail -1 | awk '{print $5}')")
        rc, out, err = run_remote(a.target, a.key, sh)
        result["findings"]["raw"] = out or err
    print(json.dumps(result, indent=2))


def cmd_health(a):
    osname = detect_os(a.target, a.key)
    h = {"target": a.target, "os": osname, "ts": int(time.time())}
    if osname == "windows":
        ps = ("$c=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average;"
              "$os=Get-CimInstance Win32_OperatingSystem;"
              "$mem=[math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/$os.TotalVisibleMemorySize*100);"
              "Write-Output ('CPU:'+$c+' MEM:'+$mem)")
        rc, out, err = run_remote(a.target, a.key, ps_encoded(ps))
        h["metrics"] = out or err
    else:
        sh = ("echo CPU:$(top -bn1 2>/dev/null | grep -i cpu | head -1);"
              "echo MEM:$(free -m 2>/dev/null | awk '/Mem:/{printf \"%d%%\", $3/$2*100}');"
              "echo DISK:$(df -h / | tail -1 | awk '{print $5}')")
        rc, out, err = run_remote(a.target, a.key, sh)
        h["metrics"] = out or err
    print(json.dumps(h, indent=2))


def load_fixes():
    if KNOWN_FIXES.exists():
        try:
            return json.loads(KNOWN_FIXES.read_text())
        except Exception:  # noqa
            return []
    return []


def score_fix(symptom, fix):
    sym = symptom.lower()
    # 1) explicit regex wins
    rx = fix.get("patternRegex")
    if rx:
        try:
            if re.search(rx, symptom, re.I):
                return float(fix.get("confidence", 0.95))
        except re.error:
            pass
    # 2) exact/substr symptom match
    pat = (fix.get("symptom") or fix.get("pattern") or "").lower()
    if pat and (pat in sym or sym in pat):
        return float(fix.get("confidence", 0.85))
    # 3) error class token match
    classes = [str(x).lower() for x in fix.get("errorClasses", [])]
    if any(c and c in sym for c in classes):
        return max(float(fix.get("confidence", 0.75)), 0.75)
    # 4) token overlap fallback
    words = set(re.findall(r"\w+", sym))
    pw = set(re.findall(r"\w+", pat))
    if words and pw:
        return round(len(words & pw) / len(words | pw), 2)
    return 0.0


def cmd_check(a):
    fixes = load_fixes()
    hits = []
    for f in fixes:
        score = score_fix(a.symptom, f)
        if score >= 0.4:
            hits.append({"score": score, **f})
    hits.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps({"matches": hits[:5]}, indent=2, ensure_ascii=False))


def cmd_log(a):
    fixes = load_fixes()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "symptom": a.symptom,
        "patternRegex": a.pattern_regex,
        "errorClasses": [x for x in (a.error_classes or '').split(',') if x],
        "cause": a.cause,
        "fix": a.fix,
        "fixType": a.fix_type,
        "risk": a.risk,
        "confidence": a.confidence,
        "platform": a.platform,
        "verifySteps": [x for x in (a.verify_steps or '').split(';;') if x],
        "rollbackSteps": [x for x in (a.rollback_steps or '').split(';;') if x],
        "target": a.target,
        "firstSeen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lastSeen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "healCount": 1,
    }
    fixes.append(entry)
    KNOWN_FIXES.parent.mkdir(parents=True, exist_ok=True)
    KNOWN_FIXES.write_text(json.dumps(fixes, indent=2, ensure_ascii=False))
    print(json.dumps({"logged": entry["id"], "total": len(fixes)}))


def cmd_list_fixes(a):
    print(json.dumps(load_fixes(), indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(prog="doctor")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_target(sp):
        sp.add_argument("--target", required=True)
        sp.add_argument("--key", default=None)
        return sp

    add_target(sub.add_parser("connect-test")).set_defaults(fn=cmd_connect_test)
    add_target(sub.add_parser("scan")).set_defaults(fn=cmd_scan)
    add_target(sub.add_parser("health")).set_defaults(fn=cmd_health)
    add_target(sub.add_parser("verify")).set_defaults(fn=cmd_verify)

    c = sub.add_parser("check"); c.add_argument("symptom"); c.set_defaults(fn=cmd_check)

    lg = sub.add_parser("log")
    lg.add_argument("--symptom", required=True)
    lg.add_argument("--cause", required=True)
    lg.add_argument("--fix", required=True)
    lg.add_argument("--fix-type", dest="fix_type", default="heal", choices=["retry", "patch", "heal"])
    lg.add_argument("--pattern-regex", default="")
    lg.add_argument("--error-classes", default="")
    lg.add_argument("--risk", default="medium", choices=["low", "medium", "high"])
    lg.add_argument("--confidence", type=float, default=0.8)
    lg.add_argument("--platform", default="any")
    lg.add_argument("--verify-steps", default="")
    lg.add_argument("--rollback-steps", default="")
    lg.add_argument("--target", default="")
    lg.set_defaults(fn=cmd_log)

    sub.add_parser("list-fixes").set_defaults(fn=cmd_list_fixes)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
