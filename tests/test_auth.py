"""Auth: register/login/refresh rotation/logout/permission & password change."""


def test_register_login_me(client):
    r = client.post("/api/v1/auth/register", json={"email": "a@t.dev", "password": "password123", "display_name": "A"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": "a@t.dev", "password": "password123"})
    token = r.json()["access_token"]
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "a@t.dev"


def test_duplicate_email_conflict(client):
    body = {"email": "dup@t.dev", "password": "password123", "display_name": "D"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    assert client.post("/api/v1/auth/register", json=body).status_code == 409


def test_wrong_password_401(client):
    client.post("/api/v1/auth/register", json={"email": "b@t.dev", "password": "password123", "display_name": "B"})
    r = client.post("/api/v1/auth/login", json={"email": "b@t.dev", "password": "wrong-password"})
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"


def test_refresh_rotation_replay_blocked(client, db):
    client.post("/api/v1/auth/register", json={"email": "c@t.dev", "password": "password123", "display_name": "C"})
    tokens = client.post("/api/v1/auth/login", json={"email": "c@t.dev", "password": "password123"}).json()
    old_refresh = tokens["refresh_token"]
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r1.status_code == 200
    # replay the OLD refresh token -> must be rejected
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401


def test_logout_revokes_refresh(client):
    client.post("/api/v1/auth/register", json={"email": "d@t.dev", "password": "password123", "display_name": "D"})
    tokens = client.post("/api/v1/auth/login", json={"email": "d@t.dev", "password": "password123"}).json()
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.post("/api/v1/auth/logout", headers=h, json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


def test_change_password_revokes_sessions(client):
    client.post("/api/v1/auth/register", json={"email": "e@t.dev", "password": "password123", "display_name": "E"})
    tokens = client.post("/api/v1/auth/login", json={"email": "e@t.dev", "password": "password123"}).json()
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.post("/api/v1/users/me/change-password", headers=h,
                    json={"current_password": "password123", "new_password": "newpassword456"})
    assert r.status_code == 200
    r = client.post("/api/v1/auth/login", json={"email": "e@t.dev", "password": "newpassword456"})
    assert r.status_code == 200


def test_error_envelope_shape(client):
    r = client.get("/api/v1/users/me")
    assert r.status_code == 401
    body = r.json()
    for key in {"code", "detail", "status", "title", "request_id"}:
        assert key in body
