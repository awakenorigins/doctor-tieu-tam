#!/usr/bin/env python3
"""Shared helpers for Doctor Tieu Tam scripts.

Single source of truth for:
  - run_remote / ssh_base
  - ps_encoded (PowerShell -EncodedCommand)
  - detect_os (safe: never blindly assumes windows on failure)
  - redact (broad secret redaction)
  - audit (append JSONL audit log)
"""
import base64, json, os, subprocess, time
from pathlib import Path

DEFAULT_KEY = str(Path.home() / ".ssh" / "doctor_tt")
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
AUDIT_LOG = WORKSPACE / "doctor-audit.jsonl"

SECRET_KEYS = (
    "apikey", "api_key", "token", "bottoken", "bot_token", "accesstoken", "access_token",
    "refreshtoken", "refresh_token", "idtoken", "id_token", "secret", "clientsecret",
    "client_secret", "password", "passphrase", "authorization", "bearer", "privatekey",
    "private_key", "cookie", "sessionkey", "session_key", "gh_token", "githubtoken",
)


def ps_encoded(ps_script):
    enc = base64.b64encode(ps_script.encode("utf-16-le")).decode()
    return "powershell -NoProfile -EncodedCommand " + enc


def ssh_base(target, key):
    return [
        "ssh", "-i", key or DEFAULT_KEY,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=15",
        "-o", "BatchMode=yes",
        target,
    ]


def run_remote(target, key, remote_cmd, timeout=40):
    try:
        p = subprocess.run(ssh_base(target, key) + [remote_cmd], capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # noqa
        return 1, "", str(e)


def detect_os(target, key):
    """Return: linux, darwin, windows, unreachable, auth_failed, timeout, unknown.

    Never assumes windows on a failed connection (shared safe implementation).
    """
    rc, out, err = run_remote(target, key, "uname -s 2>/dev/null || echo __WINPROBE__")
    low = (err or "").lower()
    if rc == 124 or "timeout" in low:
        return "timeout"
    o = (out or "").strip()
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
    return o.lower()


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
