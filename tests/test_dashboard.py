"""Dashboard addon hardening tests."""

from app.dashboard import create_app


def test_login_page_has_csrf():
    app = create_app()
    client = app.test_client()
    resp = client.get("/admin/login")
    assert resp.status_code == 200
    assert "csrf_token" in resp.get_data(as_text=True)


def test_dashboard_requires_login():
    app = create_app()
    client = app.test_client()
    assert client.get("/admin").status_code == 302


def test_forged_post_rejected():
    app = create_app()
    client = app.test_client()
    resp = client.post("/admin/login", data={"code": "1234", "csrf_token": "forged"})
    assert resp.status_code == 403


def test_wrong_code_rejected(db):
    app = create_app()
    client = app.test_client()
    client.get("/admin/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]

    resp = client.post(
        "/admin/login",
        data={"code": "0000", "csrf_token": token},
        follow_redirects=True,
    )
    assert b"\xd8\xb1\xd9\x85\xd8\xb2" in resp.data  # "رمز" in flash


def test_correct_code_logs_in(db):
    app = create_app()
    client = app.test_client()
    client.get("/admin/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]

    resp = client.post(
        "/admin/login",
        data={"code": "1234", "csrf_token": token},
        follow_redirects=True,
    )
    assert resp.status_code == 200


def test_rate_limit_blocks_after_5_attempts():
    app = create_app()
    client = app.test_client()
    client.get("/admin/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]

    for _ in range(5):
        client.post("/admin/login", data={"code": "0000", "csrf_token": token})

    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    resp = client.post("/admin/login", data={"code": "1234", "csrf_token": token})
    assert resp.status_code == 200  # shows the wait message, code ignored at 5+