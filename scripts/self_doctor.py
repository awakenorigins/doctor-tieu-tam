#!/usr/bin/env python3
"""Self Doctor — local self-diagnosis & self-heal for THIS OpenClaw machine.

Proactive mode: the agent examines its own host (no SSH needed), finds problems,
and can auto-fix the safe ones, escalating the risky ones.

Subcommands:
  selfcheck [--json]            # examine local host: gateway, ports, disk, config validity
  selfheal  [--dry-run] [--apply]  # attempt safe local fixes; default is dry-run
  watch     --interval SEC      # loop selfcheck, print only when something is wrong

Safety: dry-run by default; never deletes data; never edits credentials; backs up
config before any write; reports evidence.
"""
import argparse, json, os, shutil, subprocess, time
from pathlib import Path

HOME = Path.home()
CONFIG = HOME / ".openclaw" / "openclaw.json"
PORTS = (18789, 20128, 20131)


def sh(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:  # noqa
        return 1, "", str(e)


def check_ports():
    rc, out, _ = sh("ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null")
    listening = {p for p in PORTS if f":{p}" in out}
    return {"listening": sorted(listening), "missing": [p for p in PORTS if p not in listening]}


def check_disk():
    rc, out, _ = sh("df -h / | tail -1 | awk '{print $5}'")
    pct = out.replace("%", "").strip()
    return {"used_pct": pct, "warn": pct.isdigit() and int(pct) >= 90}


def check_gateway():
    rc, out, _ = sh("systemctl is-active openclaw-gateway 2>/dev/null")
    if out:
        return out
    rc, out, _ = sh("pgrep -f 'openclaw' >/dev/null && echo running || echo down")
    return out or "unknown"


def check_config():
    if not CONFIG.exists():
        return {"exists": False, "valid": False}
    try:
        json.loads(CONFIG.read_text())
        return {"exists": True, "valid": True}
    except Exception as e:  # noqa
        return {"exists": True, "valid": False, "error": str(e)}


def selfcheck():
    ports = check_ports()
    gw = check_gateway()
    # Some installs run OpenClaw under a user service / custom process while the
    # system service is inactive. If the gateway port is listening, treat it as
    # reachable evidence instead of raising a false critical alarm.
    gateway_reachable = 18789 in ports["listening"]
    return {
        "host": os.uname().nodename if hasattr(os, "uname") else "local",
        "ts": int(time.time()),
        "gateway": gw,
        "gateway_reachable": gateway_reachable,
        "ports": ports,
        "disk": check_disk(),
        "config": check_config(),
    }


def diagnose(report):
    problems = []
    if (not report.get("gateway_reachable")) and report["gateway"] in ("down", "failed", "inactive", "unknown"):
        problems.append({"id": "gateway_down", "severity": "critical",
                         "fix": "restart_gateway", "safe": True})
    if not report["config"].get("valid"):
        problems.append({"id": "config_invalid", "severity": "critical",
                         "fix": "restore_config_backup", "safe": True})
    if report["disk"].get("warn"):
        problems.append({"id": "disk_high", "severity": "warning",
                         "fix": "report_only", "safe": False})
    if report["ports"]["missing"]:
        problems.append({"id": "ports_missing", "severity": "warning",
                         "detail": report["ports"]["missing"], "fix": "report_only", "safe": False})
    return problems


def restore_config_backup():
    baks = sorted(CONFIG.parent.glob("openclaw.json.bak*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for b in baks:
        try:
            json.loads(b.read_text())
            shutil.copy2(CONFIG, str(CONFIG) + f".broken-{int(time.time())}")
            shutil.copy2(b, CONFIG)
            return True, f"restored from {b.name}"
        except Exception:  # noqa
            continue
    return False, "no valid backup found"


def restart_gateway():
    # Audit fix H2: issue the restart, then verify recovery by evidence instead of
    # trusting an rc that a trailing `echo done` always forced to 0.
    sh("systemctl --user restart openclaw-gateway 2>/dev/null || "
       "openclaw gateway restart 2>/dev/null", timeout=40)
    rc, out, _ = sh("ss -ltn 2>/dev/null | grep -q ':18789' && echo PORT_18789=listen; "
                    "curl -fsS -m5 http://127.0.0.1:20131/health >/dev/null 2>&1 && echo PROXY_HEALTH=200",
                    timeout=20)
    ok = "PORT_18789=listen" in out or "PROXY_HEALTH=200" in out
    return ok, (out.strip() or "restart attempted; no listener/health evidence")


def apply_fix(problem, dry_run):
    fix = problem["fix"]
    if not problem.get("safe"):
        return {"id": problem["id"], "action": "escalate", "reason": "needs human / unsafe"}
    if dry_run:
        return {"id": problem["id"], "action": "would_" + fix, "dry_run": True}
    if fix == "restart_gateway":
        ok, detail = restart_gateway()
        return {"id": problem["id"], "action": "restart_gateway", "ok": ok, "detail": detail}
    if fix == "restore_config_backup":
        ok, detail = restore_config_backup()
        return {"id": problem["id"], "action": "restore_config_backup", "ok": ok, "detail": detail}
    return {"id": problem["id"], "action": "report_only"}


def cmd_selfcheck(a):
    print(json.dumps(selfcheck(), indent=2))


def cmd_selfheal(a):
    report = selfcheck()
    problems = diagnose(report)
    dry = not a.apply
    actions = [apply_fix(p, dry) for p in problems]
    print(json.dumps({"report": report, "problems": problems, "actions": actions,
                      "mode": "dry-run" if dry else "apply"}, indent=2))


def cmd_watch(a):
    while True:
        report = selfcheck()
        problems = diagnose(report)
        if problems:
            print(json.dumps({"ts": report["ts"], "problems": problems}, ensure_ascii=False))
        time.sleep(a.interval)


def main():
    p = argparse.ArgumentParser(prog="self_doctor")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selfcheck").set_defaults(fn=cmd_selfcheck)
    sh_ = sub.add_parser("selfheal"); sh_.add_argument("--apply", action="store_true"); sh_.add_argument("--dry-run", action="store_true"); sh_.set_defaults(fn=cmd_selfheal)
    w = sub.add_parser("watch"); w.add_argument("--interval", type=int, default=300); w.set_defaults(fn=cmd_watch)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
