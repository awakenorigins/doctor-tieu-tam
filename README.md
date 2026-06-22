# 🩺 Doctor Tiểu Tâm

Remote **doctor** skill for OpenClaw agents — diagnose and heal PCs and other OpenClaw instances over **Tailscale/SSH**.

Inspired by the structure of [`psyduckler/self-healing-agents`](https://github.com/psyduckler/self-healing-agents) (Detect → Triage → Diagnose → Fix → Verify → Log), extended with cross-platform health checks and a battle-tested **remote SSH heal** workflow for OpenClaw (Windows + Linux/macOS).

## What it does

- **Connect** safely to a remote machine via Tailscale + SSH (operator-provisioned key only).
- **Scan / Health** — OS, OpenClaw gateway state, key ports (18789/20128/20131), CPU/RAM/disk.
- **Diagnose** — match against a learned `known-fixes.json`, classify root cause.
- **Heal OpenClaw** — read → backup → patch config JSON → restart gateway (no clobbering one-liners).
- **Verify** — prove the fix with real evidence (HTTP 200, service Running, proxy log shows request).
- **Learn** — append each cured case to `known-fixes.json`.

## Safety first

1. Never log in without a key the machine owner added.
2. Always back up config (`*.bak-tt-<timestamp>`) before editing.
3. Read → merge → write. Never clobber whole files.
4. Verify with evidence, not assumptions.
5. Never print secrets; redact `apiKey`/`token`/`botToken`.
6. Escalate on credential/data-loss/repeated-failure cases.

## Quick start

```bash
# 1. create a heal key, give the .pub to the machine owner to add
ssh-keygen -t ed25519 -N '' -C 'doctor-tieu-tam' -f ~/.ssh/doctor_tt
cat ~/.ssh/doctor_tt.pub

# 2. test + diagnose
python3 scripts/doctor.py connect-test --target user@host --key ~/.ssh/doctor_tt
python3 scripts/doctor.py health       --target user@host --key ~/.ssh/doctor_tt
python3 scripts/doctor.py scan         --target user@host --key ~/.ssh/doctor_tt

# 3. heal an OpenClaw runtime mismatch (Codex limit despite Claude model)
python3 scripts/openclaw_heal.py set-runtime --target user@host \
  --provider claudekkg --runtime openclaw --key ~/.ssh/doctor_tt
python3 scripts/openclaw_heal.py restart --target user@host --key ~/.ssh/doctor_tt

# 4. record the cure
python3 scripts/doctor.py log --symptom "..." --cause "..." --fix "..." --fix-type heal
```

## Files
- `SKILL.md` — full workflow + safety rules (loaded by OpenClaw)
- `scripts/doctor.py` — connect-test / scan / health / check / log / list-fixes
- `scripts/openclaw_heal.py` — get-config / backup / restart / set-runtime
- `references/openclaw-playbook.md` — common OpenClaw heal cases
- `references/error-patterns.md` — pattern → root cause → fix

## License
MIT
