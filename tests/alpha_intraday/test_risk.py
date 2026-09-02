from alpha_intraday.config import DEFAULT_CONFIG
from alpha_intraday.models import RiskCategory
from alpha_intraday.risk import build_risk_plan, risk_reward


def test_risk_sizing_account_5000_eur_integer_no_leverage():
    plan = build_risk_plan(entry=100, stop=99, risk_category=RiskCategory.LOW, eurusd=1.08, config=DEFAULT_CONFIG)
    assert plan.risk_eur == 12.5
    assert plan.shares == 13
    assert plan.notional_usd <= 5000 * 1.08
    assert plan.position_size_available is True


def test_medium_high_daily_max_and_invalid_stop():
    medium = build_risk_plan(entry=100, stop=99, risk_category=RiskCategory.MEDIUM, eurusd=1.08, config=DEFAULT_CONFIG)
    high = build_risk_plan(entry=100, stop=99, risk_category=RiskCategory.HIGH, eurusd=1.08, config=DEFAULT_CONFIG)
    bad = build_risk_plan(entry=100, stop=100, risk_category=RiskCategory.LOW, eurusd=1.08, config=DEFAULT_CONFIG)
    assert medium.risk_eur == 25
    assert high.risk_eur == 37.5
    assert bad.position_size_available is False
    assert risk_reward(100, 99, 101.5) == 1.5
