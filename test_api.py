import pytest

from Simap.api import SimapClient


def test_get_projects_uses_newest_publication_from(monkeypatch):
    client = SimapClient()
    captured_params = []

    def fake_request(method, url, params=None, **kwargs):
        captured_params.append(params or {})

        class DummyResponse:
            def json(self):
                return {"projects": [], "pagination": {}}

        return DummyResponse()

    monkeypatch.setattr(client, "_request", fake_request)

    params = {"newestPublicationFrom": "2024-01-01"}
    list(client.get_projects(params, max_pages=1, delay=0))

    assert captured_params, "Request wurde nicht aufgerufen"
    assert (
        captured_params[0].get("newestPublicationFrom") == "2024-01-01"
    )
