import pytest

from howlate_pipeline import arrivals


@pytest.fixture(autouse=True)
def inside_google_cloud(monkeypatch):
    monkeypatch.setattr(arrivals, "inside_google_cloud", lambda: True)
