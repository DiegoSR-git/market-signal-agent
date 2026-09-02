import os


def test_integration_tests_are_opt_in():
    if os.getenv("ALPHA_RUN_INTEGRATION_TESTS") != "true":
        return
    assert os.getenv("ALPACA_API_KEY"), "ALPACA_API_KEY requerida para integracion"
    assert os.getenv("ALPACA_SECRET_KEY"), "ALPACA_SECRET_KEY requerida para integracion"
