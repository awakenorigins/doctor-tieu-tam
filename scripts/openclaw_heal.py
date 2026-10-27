#!/usr/bin/env python3
"""Helpers to heal a remote OpenClaw instance over SSH.

Safe ops only: read config, back it up, patch JSON keys, restart gateway.
Never prints secret values; redaction is centralized in common.py (audit fix H3).

Usage:
  openclaw_heal.py get-config   --target user@host [--key PATH]
  openclaw_heal.py backup       --target user@host [--key PATH]
  openclaw_heal.py restart      --target user@host [--key PATH] [--os windows|linux]
  openclaw_heal.py set-runtime  --target user@host --provider claudekkg --runtime openclaw [--key PATH]

This module performs the read/transform/write on the GATEWAY side: it pulls the
remote config text, edits JSON in Python, then writes it back. It does NOT run
clobbering one-liners on the remote host.

Audit fixes:
  H1 — uses the shared hardened detect_os; aborts when host is not in a known-good
       state (auth_failed/unreachable/timeout/unknown) instead of assuming windows.
  H2 — restart is judged by real evidence (verify_gateway), never a masked rc.
  H3 — redaction is shared (key-substring + value scanning).
  M3 — config write is atomic (temp file + rename).
"""
import argparse, base64, json, os, shlex, sys, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from common import (run_remote, detect_os, NON_OK_OS, redact, audit, verify_gateway)  # type: ignore
except Exception:  # noqa
    import importlib.util
    _spec = importlib.util.spec_from_file_location("_doctor_common", str(Path(__file__).with_name("common.py")))
    _c = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_c)
    run_remote, detect_os, NON_OK_OS = _c.run_remote, _c.detect_os, _c.NON_OK_OS
    redact, audit, verify_gateway = _c.redact, _c.audit, _c.verify_gateway


def run(target, key, remote_cmd, timeout=45):
    # Thin wrapper kept for call-site compatibility; uses shared SSH transport.
    return run_remote(target, key, remote_cmd, timeout)


def remote_config_path(osname):
    if osname == "windows":
        return r"$env:USERPROFILE\.openclaw\openclaw.json"
    return "$HOME/.openclaw/openclaw.json"


def read_config(target, key, osname):
    if osname == "windows":
        ps = f"Get-Content {remote_config_path(osname)} -Raw"
        rc, out, err = run(target, key, "powershell -NoProfile -Command " + shlex.quote(ps))
    else:
        rc, out, err = run(target, key, "cat $HOME/.openclaw/openclaw.json")
    if rc != 0:
        raise RuntimeError(err or "read failed")
    return out


def write_config(target, key, osname, text):
    """Atomic write (audit M3): write a temp file then rename over the target."""
    b64 = base64.b64encode(text.encode()).decode()
    if osname == "windows":
        ps = ("$dst=\"$env:USERPROFILE\\.openclaw\\openclaw.json\";"
              "$tmp=$dst + '.tmp-tt';"
              "$b=[System.Convert]::FromBase64String('" + b64 + "');"
              "[System.IO.File]::WriteAllBytes($tmp,$b);"
              "Move-Item -Force $tmp $dst")
        rc, out, err = run(target, key, "powershell -NoProfile -Command " + shlex.quote(ps))
    else:
        rc, out, err = run(target, key,
                           f"echo {shlex.quote(b64)} | base64 -d > $HOME/.openclaw/openclaw.json.tmp-tt && "
                           f"mv -f $HOME/.openclaw/openclaw.json.tmp-tt $HOME/.openclaw/openclaw.json")
    if rc != 0:
        raise RuntimeError(err or "write failed")


def backup(target, key, osname):
    ts = time.strftime("%Y%m%d-%H%M%S")
    if osname == "windows":
        ps = (f"Copy-Item \"$env:USERPROFILE\\.openclaw\\openclaw.json\" "
              f"\"$env:USERPROFILE\\.openclaw\\openclaw.json.bak-tt-{ts}\" -Force; echo OK")
        rc, out, err = run(target, key, "powershell -NoProfile -Command " + shlex.quote(ps))
    else:
        rc, out, err = run(target, key,
                           f"cp $HOME/.openclaw/openclaw.json $HOME/.openclaw/openclaw.json.bak-tt-{ts}; echo OK")
    return rc == 0, f"openclaw.json.bak-tt-{ts}"


def restart_gateway(target, key, osname):
    # Audit fix H2: never trust the restart command's own rc (it was masked by a
    # trailing `echo done`). Issue the restart, then PROVE recovery with evidence.
    if osname == "windows":
        ps = ("Stop-ScheduledTask -TaskName 'OpenClaw Gateway';Start-Sleep 3;"
              "Start-ScheduledTask -TaskName 'OpenClaw Gateway';Start-Sleep 2")
        run(target, key, "powershell -NoProfile -Command " + shlex.quote(ps), timeout=60)
    else:
        run(target, key,
            "systemctl --user restart openclaw-gateway 2>/dev/null || "
            "openclaw gateway restart 2>/dev/null", timeout=60)
    return verify_gateway(target, key, osname)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("get-config", "backup", "restart"):
        sp = sub.add_parser(name); sp.add_argument("--target", required=True); sp.add_argument("--key", default=None); sp.add_argument("--os", default=None)
    sr = sub.add_parser("set-runtime")
    sr.add_argument("--target", required=True); sr.add_argument("--key", default=None); sr.add_argument("--os", default=None)
    sr.add_argument("--provider", required=True); sr.add_argument("--runtime", default="openclaw")
    a = p.parse_args()

    osname = a.os or detect_os(a.target, a.key)

    # Audit fix H1: abort heal/write when host is not in a known-good state.
    if osname in NON_OK_OS:
        print(json.dumps({"ok": False, "error": f"host_{osname}",
                          "hint": "aborting heal: host is not in a known-good state",
                          "target": a.target}))
        return

    if a.cmd == "get-config":
        cfg = json.loads(read_config(a.target, a.key, osname))
        print(json.dumps(redact(cfg), indent=2, ensure_ascii=False))
    elif a.cmd == "backup":
        ok, name = backup(a.target, a.key, osname)
        print(json.dumps({"ok": ok, "backup": name}))
    elif a.cmd == "restart":
        ok, state = restart_gateway(a.target, a.key, osname)
        print(json.dumps({"ok": ok, "evidence": state}))
    elif a.cmd == "set-runtime":
        ok, bname = backup(a.target, a.key, osname)
        cfg = json.loads(read_config(a.target, a.key, osname))
        prov = cfg.get("models", {}).get("providers", {}).get(a.provider)
        if prov is None:
            print(json.dumps({"ok": False, "error": f"provider {a.provider} not found"})); return
        prov["agentRuntime"] = {"id": a.runtime}
        models = cfg.get("agents", {}).get("defaults", {}).get("models", {})
        for mk in list(models.keys()):
            if mk.startswith(a.provider + "/"):
                models[mk] = {**(models[mk] or {}), "agentRuntime": {"id": a.runtime}}
        write_config(a.target, a.key, osname, json.dumps(cfg, indent=2, ensure_ascii=False))
        audit({"action": "set-runtime", "target": a.target, "provider": a.provider,
               "runtime": a.runtime, "backup": bname, "os": osname})
        print(json.dumps({"ok": True, "backup": bname, "provider": a.provider, "runtime": a.runtime}))


if __name__ == "__main__":
    main()
