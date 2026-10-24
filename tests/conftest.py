from __future__ import annotations

import pytest

from hedgeproof.config import load_settings
from hedgeproof.data import build_period_table
from hedgeproof.synthetic import synthetic_market


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def market():
    """SYNTHETIC market data (labelled; never used for empirical claims)."""
    return synthetic_market()


@pytest.fixture(scope="session")
def table(market, settings):
    return build_period_table(market, settings.experiment)
