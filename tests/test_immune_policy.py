import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('immune', ROOT / 'scripts' / 'immune.py')
immune = importlib.util.module_from_spec(spec); spec.loader.exec_module(immune)

def ab(status='trusted', risk='low', verify=('gateway_running',), rollback=('restore',)):
    return {'status': status, 'fixPlan': {'risk': risk}, 'verifyPlan': list(verify), 'rollbackPlan': list(rollback)}

def test_high_risk_never_autoheals():
    ok, reason = immune.auto_policy(ab(risk='high'), 0.99)
    assert not ok and reason == 'high_risk_diagnose_only'

def test_medium_risk_requires_approval():
    ok, reason = immune.auto_policy(ab(risk='medium'), 0.99)
    assert not ok and reason == 'medium_risk_requires_approval'

def test_candidate_not_auto():
    ok, reason = immune.auto_policy(ab(status='candidate'), 0.99)
    assert not ok and reason == 'candidate_requires_dry_run_or_human'

def test_no_verify_no_autoheal():
    ok, reason = immune.auto_policy(ab(verify=()), 0.99)
    assert not ok and reason == 'no_verify_plan'

def test_trusted_low_high_confidence_auto():
    ok, reason = immune.auto_policy(ab(), 0.9)
    assert ok and reason == 'auto_safe'

def test_negative_signal_blocks():
    cand = {'match': {'patternRegex': ['(?i)codex'], 'requiredSignals': [], 'negativeSignals': ['actual_codex_provider_selected']}}
    sc = immune.component_scores('codex usage limit', cand, evidence=['actual_codex_provider_selected'])
    assert sc['evidenceScore'] == 0.0
