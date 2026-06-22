import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('immune', ROOT / 'scripts' / 'immune.py')
immune = importlib.util.module_from_spec(spec)
spec.loader.exec_module(immune)

def test_antibody_regex_score():
    ab = {'match': {'patternRegex': ['(?i)codex.*usage limit.*claude']}, 'confidence': 0.88}
    sc = immune.component_scores('Codex usage limit after selecting Claude model', ab)
    assert sc['patternScore'] == 1.0
    assert sc['confidence'] > 0.5

def test_token_score_fallback():
    ab = {'name': 'gateway down port missing', 'diagnosis': 'OpenClaw gateway stopped'}
    sc = immune.component_scores('gateway stopped', ab)
    assert sc['patternScore'] > 0

def test_no_rollback_no_autoheal():
    ab = {'status': 'trusted', 'fixPlan': {'risk': 'low'}, 'verifyPlan': ['gateway_running'], 'rollbackPlan': []}
    ok, reason = immune.auto_policy(ab, 0.99)
    assert not ok
    assert reason == 'no_verified_rollback'
