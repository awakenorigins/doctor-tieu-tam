# Example: Doctor Immune Loop

A healed case becomes an antibody so future agents can recover faster.

## 1. Record the incident

```bash
python3 scripts/immune.py record-incident \
  --symptom "Claude model selected but Codex usage limit appears" \
  --cause "The model changed but the runtime remained Codex" \
  --fix "Set agentRuntime.id=openclaw for provider/model and restart gateway" \
  --verify "Gateway running;;Proxy receives POST /v1/chat/completions;;Bot replies" \
  --risk low --platform windows
```

## 2. Learn an antibody

```bash
python3 scripts/immune.py learn --incident inc-xxxx \
  --name "Runtime mismatch: selected Claude but still Codex" \
  --risk low --confidence 0.85
```

## 3. Match future symptoms

```bash
python3 scripts/immune.py match --symptom "Bot says Codex usage limit after I selected Claude"
```

## 4. Apply conservatively

```bash
python3 scripts/immune.py apply-known-fix --symptom "Codex limit after Claude model" --dry-run
```

Low-risk/high-confidence fixes can later become auto-heal candidates. Medium/high-risk fixes stay human-reviewed.
