"""Shared hermetic Home Assistant fixtures."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow this repository's custom integration to load."""
    yield
