# 🩺 Doctor Tieu Tam

> Turn your AI agent into a **remote doctor** that diagnoses and heals broken PCs and other OpenClaw instances — safely, over Tailscale/SSH.

Your bot freezes at 2 AM. You're not home. The machine is across the city.
With **Doctor Tieu Tam**, your agent just... fixes it. By itself. Safely.

---

## Why this exists

Most "self-healing" tools either retry blindly or need you sitting at the keyboard. This one is different: it does **real root-cause diagnosis and permanent fixes on remote machines**, and it refuses to be reckless while doing it.

Inspired by [`psyduckler/self-healing-agents`](https://github.com/psyduckler/self-healing-agents) (Detect → Triage → Diagnose → Fix → Verify → Log), extended with cross-platform health checks and a **battle-tested remote SSH heal flow** for OpenClaw on Windows + Linux/macOS.

## What it does

🔌 **Connects safely** to a remote machine over Tailscale + SSH (only with a key the owner installed).
🩺 **Examines** the patient — OS, OpenClaw gateway state, key ports, CPU/RAM/disk.
🔎 **Diagnoses** the real root cause (matches a learned `known-fixes.json` first).
💾 **Backs up** before touching anything.
🛠️ **Heals** the OpenClaw config (read → patch → restart) — no clobbering one-liners.
✅ **Verifies** with real evidence: HTTP 200, service `Running`, proxy log shows the request.
🧠 **Learns** — every cured case is saved so the next fix is faster.

## Effectiveness — a real case

A remote PC ran an AI bot that **"had the right model selected but still wouldn't run."** The agent SSH'd in, traced it to a runtime misconfiguration, backed up the config, patched it, restarted the gateway, and confirmed the bot was answering through the right model — **without a human touching that machine.**

## Safety first (this is the point)

1. 🔒 **Never logs in** without a key the machine owner added.
2. 💾 **Always backs up** (`*.bak-tt-<timestamp>`) before any change.
3. 🧩 **Reads → merges → writes.** Never overwrites whole files blindly.
4. 🧪 **Proves the fix** with evidence — never claims "fixed" on faith.
5. 🙅 **Never touches** credentials/API keys on its own.
6. 🤐 **Never prints secrets** — `apiKey`/`token`/`botToken` are redacted.
7. 🚨 **Escalates** on credential, data-loss, or repeated-failure cases.

> An agent that can fix machines is powerful. An agent that knows when **not** to act is trustworthy. Doctor Tieu Tam is built to be both.

## Quick start

```bash
# 1. create a heal key; give the .pub to the machine owner to add
ssh-keygen -t ed25519 -N '' -C 'doctor-tieu-tam' -f ~/.ssh/doctor_tt
cat ~/.ssh/doctor_tt.pub

# 2. examine the patient
python3 scripts/doctor.py connect-test --target user@host --key ~/.ssh/doctor_tt
python3 scripts/doctor.py health       --target user@host --key ~/.ssh/doctor_tt
python3 scripts/doctor.py scan         --target user@host --key ~/.ssh/doctor_tt

# 3. heal an OpenClaw runtime mismatch (e.g. "Codex limit" despite a Claude model)
python3 scripts/openclaw_heal.py set-runtime --target user@host \
  --provider claudekkg --runtime openclaw --key ~/.ssh/doctor_tt
python3 scripts/openclaw_heal.py restart --target user@host --key ~/.ssh/doctor_tt

# 4. record the cure so it's faster next time
python3 scripts/doctor.py log --symptom "..." --cause "..." --fix "..." --fix-type heal
```

## Files
- `SKILL.md` — full workflow + safety rules (loaded by OpenClaw)
- `scripts/doctor.py` — connect-test / scan / health / check / log / list-fixes
- `scripts/openclaw_heal.py` — get-config / backup / restart / set-runtime
- `references/openclaw-playbook.md` — common OpenClaw heal cases
- `references/error-patterns.md` — pattern → root cause → fix

## Install as an OpenClaw skill
Drop this folder into your OpenClaw `skills/` directory. The agent picks it up via `SKILL.md`.

## License
MIT — free to use, fork, and share. If it helps you, a ⭐ goes a long way. 🙏

## v0.2 hardening

After an external audit, Doctor Tieu Tam gained several production-safety upgrades:

- `verify` is now real: gateway/task state, port evidence, and health probes.
- OS detection is safer: SSH/auth/network failures are no longer mislabeled as Windows.
- Secret redaction is broader: access tokens, refresh tokens, authorization headers, cookies, private keys, etc.
- `self_doctor.py` adds **local self-check / self-heal** mode so an agent can proactively examine its own host.
- Known fixes support regex, confidence, risk, platform, verify steps, rollback steps.
- `openclaw_heal.py` writes an audit log (`doctor-audit.jsonl`) for heal operations.
- Basic pytest coverage for redaction, matching, and safe OS detection.

```bash
python3 scripts/doctor.py verify --target user@host --key ~/.ssh/doctor_tt
python3 scripts/self_doctor.py selfcheck
python3 scripts/self_doctor.py selfheal          # dry-run by default
python3 scripts/self_doctor.py selfheal --apply  # only safe fixes
```
