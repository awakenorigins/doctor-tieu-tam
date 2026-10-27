# doctor-tieu-tam — Remote diagnostics and healing for OpenClaw instances

> Connect to any OpenClaw machine via Tailscale or SSH, diagnose the root cause of failures, apply safe fixes, verify with real evidence, and log known solutions for next time.

[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-blueviolet)](https://github.com/NachaFromMars)

## Overview
doctor-tieu-tam is a remote-healing skill for PCs and OpenClaw instances. It follows a structured pipeline: connect securely → inspect health → read logs → diagnose root cause → backup → fix → verify with real evidence → log to `known-fixes.json`. Every fix is verified with concrete proof (HTTP 200, service Running), and every resolved case is logged so future fixes run faster. Safety rules are strict: never access without owner-provided credentials, always backup before any config change.

## Pipeline
1. **Connect** — `tailscale status` → SSH with dedicated key
2. **Inspect** — system health check
3. **Read logs** — identify error signals
4. **Diagnose** — root cause analysis
5. **Backup** — copy config files with `.bak-tt-<timestamp>`
6. **Fix** — targeted change, never clobber whole files
7. **Verify** — `curl 200`, service Running — real evidence only
8. **Log** — update `known-fixes.json`

## Safety Rules
- No access without owner-provided SSH key or credentials
- Always backup before changing config
- Escalate when touching credentials, API keys, or data-loss risk

## Trigger Keywords (OpenClaw)
heal PC, fix openclaw remotely, gateway down, machine not responding, ssh fix, doctor, chẩn đoán lỗi

---
Part of the [NachaFromMars](https://github.com/NachaFromMars) OpenClaw skill ecosystem.
