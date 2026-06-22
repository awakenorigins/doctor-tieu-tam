# Example: local self-doctor

Run on the same machine as the agent:

```bash
python3 scripts/self_doctor.py selfcheck
python3 scripts/self_doctor.py selfheal
```

`selfheal` is dry-run by default. It reports safe actions it would take, and escalates risky ones.

```bash
python3 scripts/self_doctor.py selfheal --apply
```

Only safe fixes are applied automatically.
