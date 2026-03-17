"""
Pytest configuration and fixtures for PE Org-AI-R Platform tests.
"""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def disable_redis():
    """
    Disable Redis caching for all tests.
    
    This prevents tests from using real cached data and ensures
    tests use mocked database responses.
    """
    try:
        with patch("app.services.redis_cache.get_redis_client", return_value=None):
            yield
    except (AttributeError, ModuleNotFoundError):
        # CS4 tests don't use app.services.redis_cache — skip gracefully
        yield
