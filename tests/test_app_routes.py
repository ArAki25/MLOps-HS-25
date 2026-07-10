"""Flask-Routen-Tests mit gemockter Datenschicht (kein Supabase nötig)."""


def test_index_renders(client):
    assert client.get('/').status_code == 200


def test_publications_requires_login(client):
    r = client.get('/publications')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_publications_renders_when_logged_in(logged_in_client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, 'is_onboarding_complete', lambda uid: True)
    monkeypatch.setattr(app_module, 'get_user_profile', lambda uid: {'company_name': 'Test AG'})
    assert logged_in_client.get('/publications').status_code == 200


def test_api_mutations_require_login(client):
    assert client.post('/api/favorites/add', json={}).status_code == 401
    assert client.post('/api/feed-rate', json={}).status_code == 401
    assert client.post('/api/profile/update', json={}).status_code == 401
    assert client.post('/api/onboarding/profile', json={}).status_code == 401


def test_admin_redirects_to_login(client):
    r = client.get('/admin')
    assert r.status_code == 302
    assert '/admin/login' in r.headers['Location']


def test_admin_login_wrong_credentials(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, 'get_admin_by_email', lambda email: None)
    r = client.post('/admin/login', data={'email': 'x@y.ch', 'password': 'nope'})
    assert r.status_code == 200
    assert 'Falsche Anmeldedaten' in r.get_data(as_text=True)


def test_admin_login_plaintext_triggers_rehash(client, app_module, monkeypatch):
    from security import is_bcrypt_hash

    admin_row = {'email': 'admin@sajf.ch', 'password': 'klartext', 'name': 'Admin'}
    rehashed: dict = {}

    monkeypatch.setattr(app_module, 'get_admin_by_email', lambda email: admin_row)
    monkeypatch.setattr(
        app_module, 'update_admin_password',
        lambda email, h: rehashed.update({'email': email, 'hash': h}) or True,
    )

    r = client.post('/admin/login', data={'email': 'admin@sajf.ch', 'password': 'klartext'})
    assert r.status_code == 302
    assert rehashed['email'] == 'admin@sajf.ch'
    assert is_bcrypt_hash(rehashed['hash'])


def test_admin_login_bcrypt_no_rehash(client, app_module, monkeypatch):
    from security import hash_password

    admin_row = {'email': 'admin@sajf.ch', 'password': hash_password('pw'), 'name': 'Admin'}
    monkeypatch.setattr(app_module, 'get_admin_by_email', lambda email: admin_row)
    monkeypatch.setattr(
        app_module, 'update_admin_password',
        lambda email, h: (_ for _ in ()).throw(AssertionError('rehash darf nicht passieren')),
    )
    r = client.post('/admin/login', data={'email': 'admin@sajf.ch', 'password': 'pw'})
    assert r.status_code == 302


def test_bob_chat_requires_message(client):
    r = client.post('/api/bob/chat', json={})
    assert r.status_code == 400


def test_bob_chat_without_api_key_falls_back(client, monkeypatch):
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    r = client.post('/api/bob/chat', json={'message': 'Hallo'})
    assert r.status_code == 200
    assert 'nicht verfügbar' in r.get_json()['reply']


def test_removed_legacy_routes_are_gone(client):
    assert client.post('/api/onboarding/ratings', json={}).status_code == 404
    assert client.get('/api/onboarding/random-tenders').status_code == 404
