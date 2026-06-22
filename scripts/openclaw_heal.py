#!/usr/bin/env python3
"""Helpers to heal a remote OpenClaw instance over SSH.

Safe ops only: read config, back it up, patch JSON keys, restart gateway.
Never prints secret values; redacts apiKey/token/botToken on display.

Usage:
  openclaw_heal.py get-config   --target user@host [--key PATH]
  openclaw_heal.py backup       --target user@host [--key PATH]
  openclaw_heal.py restart      --target user@host [--key PATH] [--os windows|linux]
  openclaw_heal.py set-runtime  --target user@host --provider claudekkg --runtime openclaw [--key PATH]

This module performs the read/transform/write on the GATEWAY side: it pulls the
remote config text, edits JSON in Python, then writes it back. It does NOT run
clobbering one-liners on the remote host.
"""
import argparse, json, os, shlex, subprocess, time
from pathlib import Path

DEFAULT_KEY = str(Path.home() / ".ssh" / "doctor_tt")
AUDIT_LOG = Path(os.environ.get("OPENCLAW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace"))) / "doctor-audit.jsonl"
SECRET_KEYS = (
    "apikey", "api_key", "token", "bottoken", "bot_token", "accesstoken", "access_token",
    "refreshtoken", "refresh_token", "idtoken", "id_token", "secret", "clientsecret",
    "client_secret", "password", "passphrase", "authorization", "bearer", "privatekey",
    "private_key", "cookie", "sessionkey", "session_key", "gh_token", "githubtoken",
)


def ssh(target, key):
    return ["ssh", "-i", key or DEFAULT_KEY, "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", target]


def run(target, key, remote_cmd, timeout=45):
    p = subprocess.run(ssh(target, key) + [remote_cmd], capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def detect_os(target, key):
    """Safe OS detection (shared logic).

    Falls back to a local safe probe if scripts.common is unavailable. NEVER
    blindly assumes windows on a failed/auth/timeout connection (audit gai #2).
    """
    try:
        from common import detect_os as _safe_detect_os  # type: ignore
    except Exception:  # noqa
        import importlib.util
        spec = importlib.util.spec_from_file_location("_doctor_common", str(Path(__file__).with_name("common.py")))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        _safe_detect_os = mod.detect_os
    return _safe_detect_os(target, key)


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
    import base64
    b64 = base64.b64encode(text.encode()).decode()
    if osname == "windows":
        ps = ("$b=[System.Convert]::FromBase64String('" + b64 + "');"
              "[System.IO.File]::WriteAllBytes(\"$env:USERPROFILE\\.openclaw\\openclaw.json\",$b)")
        rc, out, err = run(target, key, "powershell -NoProfile -Command " + shlex.quote(ps))
    else:
        rc, out, err = run(target, key,
                           f"echo {shlex.quote(b64)} | base64 -d > $HOME/.openclaw/openclaw.json")
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
    if osname == "windows":
        ps = ("Stop-ScheduledTask -TaskName 'OpenClaw Gateway';Start-Sleep 3;"
              "Start-ScheduledTask -TaskName 'OpenClaw Gateway';Start-Sleep 2;"
              "(Get-ScheduledTask -TaskName 'OpenClaw Gateway').State")
        rc, out, err = run(target, key, "powershell -NoProfile -Command " + shlex.quote(ps))
    else:
        rc, out, err = run(target, key,
                           "systemctl --user restart openclaw-gateway 2>/dev/null || openclaw gateway restart 2>/dev/null; echo done")
    return rc == 0, (out or err).strip()


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("***REDACTED***" if k.lower() in SECRET_KEYS else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def audit(event):
    event = {**event, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


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

    if a.cmd == "get-config":
        cfg = json.loads(read_config(a.target, a.key, osname))
        print(json.dumps(redact(cfg), indent=2, ensure_ascii=False))
    elif a.cmd == "backup":
        ok, name = backup(a.target, a.key, osname)
        print(json.dumps({"ok": ok, "backup": name}))
    elif a.cmd == "restart":
        ok, state = restart_gateway(a.target, a.key, osname)
        print(json.dumps({"ok": ok, "state": state}))
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
