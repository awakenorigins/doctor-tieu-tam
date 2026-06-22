# Changelog

## v0.3.0 — GitHub polish pack
- Repositioned project as **Self & Remote Doctor for Agents**.
- Added clearer README hero, badges, architecture diagram, safety model, use cases, and real-world example.
- Added examples, issue templates, PR template, SECURITY, and CONTRIBUTING.

## v0.2.1 — CI and packaging cleanup
- Added GitHub Actions CI.
- Added `scripts/__init__.py` and cleaner `.gitignore`.

## v0.2.0 — Hardening release
- Added real `verify` command.
- Safer OS detection (`auth_failed`, `unreachable`, `timeout`, `unknown`).
- Added `self_doctor.py` for local self-check/self-heal.
- Broader secret redaction.
- Known-fixes schema with regex/confidence/risk/platform/verify/rollback metadata.
- Added audit log and tests.

## v0.1.0 — Initial release
- Remote OpenClaw doctor prototype: SSH/Tailscale, scan/health, config backup/patch, known-fixes.
