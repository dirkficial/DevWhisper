import pytest

# Run all async test functions automatically without needing @pytest.mark.asyncio
# on every test. Requires pytest-asyncio >= 0.21.
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark a test as async (handled by pytest-asyncio)"
    )
