import importlib.util
from pathlib import Path


path = Path(__file__).resolve().parents[1] / 'deploy/vps-observability/raise-acquisition-budgets.py'
spec = importlib.util.spec_from_file_location('raise_acquisition_budgets', path)
budgets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budgets)


def test_rewrite_preserves_unrelated_secret_and_sets_consistent_finite_caps():
    raw = 'SECRET_KEY=private\n' + ''.join(key + '=' + value + '\n' for key, value in budgets.EXPECTED.items())
    result = budgets.rewrite(raw)
    assert result.startswith('SECRET_KEY=private\n')
    assert 'RUNR_ACQUISITION_MAX_REQUESTS=1200\n' in result
    assert budgets.rewrite(result) == result
    assert sum(int(budgets.TARGET[key]) for key in ('RUNR_LINKEDIN_MAX_REQUESTS', 'RUNR_EMPLOYER_MAX_REQUESTS')) == 1200


def test_unexpected_budget_refuses_overwrite():
    raw = ''.join(key + '=' + ('999' if key == 'RUNR_LINKEDIN_MAX_REQUESTS' else value) + '\n'
                  for key, value in budgets.EXPECTED.items())
    try:
        budgets.rewrite(raw)
    except ValueError as error:
        assert str(error) == 'unexpected_budget_value:RUNR_LINKEDIN_MAX_REQUESTS'
    else:
        raise AssertionError('Expected an explicit refusal')
