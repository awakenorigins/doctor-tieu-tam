import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('immune', ROOT / 'scripts' / 'immune.py')
immune = importlib.util.module_from_spec(spec)
spec.loader.exec_module(immune)

def test_antibody_regex_score():
    ab = {'patternRegex': '(?i)codex.*usage limit.*claude', 'confidence': 0.88}
    assert immune.score('Codex usage limit after selecting Claude model', ab) == 0.88

def test_token_score_fallback():
    ab = {'name': 'gateway down port missing', 'diagnosis': 'OpenClaw gateway stopped'}
    assert immune.score('gateway stopped', ab) > 0
