import os

# Tests never touch a real database. Set before any app import;
# load_dotenv does not override variables that already exist.
os.environ["DATABASE_URL"] = ""

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """No test reaches Copernicus; every test starts with empty caches."""
    from app import routes
    from app.sim import snapshot

    def refuse(key):
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(snapshot, "fetch_copernicus", refuse)
    monkeypatch.setattr(snapshot, "_copernicus_down_until", 0.0)
    snapshot._cache.clear()
    routes._runs.clear()
