from pathlib import Path


def test_alpha_schedule_is_disabled_by_default_but_manual_dispatch_exists():
    workflow = Path(".github/workflows/alpha-intraday.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "github.event_name != 'schedule' || vars.ALPHA_SCHEDULE_ENABLED == 'true'" in workflow
    assert "ALPHA_DATA_PROVIDER: ${{ vars.ALPHA_DATA_PROVIDER || 'mock' }}" in workflow
