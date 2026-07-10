"""Gemeinsame Fixtures. Setzt Dummy-Env VOR jedem App-Import,
damit die Tests ohne .env / ohne Supabase-Verbindung laufen (CI)."""

import os

import pytest

os.environ.setdefault('SUPABASE_URL', 'https://example.supabase.co')
os.environ.setdefault('SUPABASE_ANON_KEY', 'test-anon-key')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')


@pytest.fixture()
def app_module(monkeypatch):
    """Importiert simap_ui/app.py mit neutralisiertem Supabase-Zugriff."""
    import supabase_client

    monkeypatch.setattr(supabase_client, 'init_supabase', lambda: None)
    import app

    app.app.config['TESTING'] = True
    return app


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture()
def logged_in_client(client):
    with client.session_transaction() as sess:
        sess['user_logged_in'] = True
        sess['user_id'] = 'test-user-id'
        sess['user_email'] = 'test@example.com'
    return client
