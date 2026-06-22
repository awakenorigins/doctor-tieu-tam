#!/usr/bin/env python3
"""Shared helpers for Doctor Tieu Tam scripts (single source of truth).

Centralizes:
  - run_remote / ssh_base                 (SSH transport)
  - ps_encoded                            (PowerShell -EncodedCommand)
  - detect_os                             (safe: never assumes windows on failure)
  - NON_OK_OS                             (states unsafe to heal/write)
  - verify_gateway                        (H2: prove restart recovery by evidence)
  - redact / _is_secret_key / _redact_str (H3: key-substring + value scanning)
  - audit                                 (append JSONL audit log)
"""
import base64, json, os, re, subprocess, time
from pathlib import Path

DEFAULT_KEY = str(Path.home() / ".ssh" / "doctor_tt")
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", str(Path.home() / ".openclaw" / "workspace")))
AUDIT_LOG = WORKSPACE / "doctor-audit.jsonl"

# Host states in which it is UNSAFE to proceed with a heal/write (audit fix H1).
NON_OK_OS = ("unreachable", "auth_failed", "timeout", "unknown")

# Audit fix H3: match key NAMES by substring (catch prefixed variants like
# "openaiApiKey") and also scan string VALUES for token-shaped secrets so a token
# embedded in a URL / Authorization header cannot leak under an innocuous key.
SECRET_KEY_SUBSTRINGS = (
    "apikey", "api_key", "token", "secret", "password", "passwd", "passphrase",
    "authorization", "oauth", "bearer", "cookie", "session", "credential",
    "privatekey", "private_key", "accesskey", "access_key",
)

_SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),                       # OpenAI-style keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),                  # GitHub tokens
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{8,}"),                # Slack tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                        # AWS access key id
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+", re.I),           # Authorization bearer
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),          # PEM private key
    re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWT
]

# secret=... inside query/connection strings (mask only the value part)
_QS_SECRET = re.compile(
    r"\b((?:token|api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|"
    r"passwd|auth|sig|signature|bearer|key)=)[^&\s\"']+",
    re.I,
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


def verify_gateway(target, key, osname):
    """Audit fix H2: prove gateway recovery with real evidence (port/health/state)."""
    if osname == "windows":
        ps = ("$s=(Get-ScheduledTask -TaskName 'OpenClaw Gateway' -EA SilentlyContinue).State;"
              "if($s){'STATE='+$s};"
              "$p=Get-NetTCPConnection -State Listen -LocalPort 18789 -EA SilentlyContinue;"
              "if($p){'PORT_18789=listen'}")
        rc, out, err = run_remote(target, key, ps_encoded(ps), timeout=25)
        ok = "STATE=Running" in (out or "") or "PORT_18789=listen" in (out or "")
    else:
        sh = ("ss -ltn 2>/dev/null | grep -q ':18789' && echo PORT_18789=listen; "
              "curl -fsS -m5 http://127.0.0.1:20131/health >/dev/null 2>&1 && echo PROXY_HEALTH=200")
        rc, out, err = run_remote(target, key, sh, timeout=25)
        ok = "PORT_18789=listen" in (out or "") or "PROXY_HEALTH=200" in (out or "")
    return ok, (out or err).strip()


def _is_secret_key(name):
    n = str(name).lower()
    return any(s in n for s in SECRET_KEY_SUBSTRINGS)


def _redact_str(s):
    for p in _SECRET_VALUE_PATTERNS:
        if p.search(s):
            return "***REDACTED***"
    return _QS_SECRET.sub(r"\1***REDACTED***", s)


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("***REDACTED***" if _is_secret_key(k) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    if isinstance(obj, str):
        return _redact_str(obj)
    return obj


def audit(event):
    event = {**event, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
