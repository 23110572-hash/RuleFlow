"""Auth (register/login/me) and data-source connection tests. No network."""
from __future__ import annotations

import os
import tempfile


def test_register_login_me_flow(client):
    reg = client.post("/auth/register", json={
        "email": "officer@synthbroker.in", "password": "secret123", "full_name": "A Officer",
        "firm": {"name": "Synthetic Securities Pvt Ltd", "category": "stockbroker", "tier": "non-QSB"},
    })
    assert reg.status_code == 200, reg.text
    body = reg.json()
    assert body["token"]
    assert body["firm"]["name"] == "Synthetic Securities Pvt Ltd"
    token = body["token"]

    # duplicate email rejected
    dup = client.post("/auth/register", json={
        "email": "officer@synthbroker.in", "password": "secret123",
        "firm": {"name": "X", "category": "stockbroker"},
    })
    assert dup.status_code == 409

    # login
    login = client.post("/auth/login", json={"email": "officer@synthbroker.in", "password": "secret123"})
    assert login.status_code == 200

    # wrong password
    bad = client.post("/auth/login", json={"email": "officer@synthbroker.in", "password": "nope"})
    assert bad.status_code == 401

    # me with token
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "officer@synthbroker.in"

    # me without token
    assert client.get("/auth/me").status_code == 401


def test_data_source_connect_real_sqlite(client):
    reg = client.post("/auth/register", json={
        "email": "ds@synthbroker.in", "password": "secret123",
        "firm": {"name": "DS Broker", "category": "stockbroker"},
    }).json()
    headers = {"Authorization": f"Bearer {reg['token']}"}

    # Build a real sqlite db with a table to connect to.
    src = os.path.join(tempfile.gettempdir(), "broker_source.db")
    if os.path.exists(src):
        os.remove(src)
    import sqlite3
    con = sqlite3.connect(src)
    con.execute("CREATE TABLE margin_reports (id INTEGER, note TEXT, pct REAL, captured TEXT)")
    con.execute("INSERT INTO margin_reports VALUES (1, 'March report', 25.0, '2026-03-31')")
    con.commit()
    con.close()

    uri = f"sqlite:///{src}"
    test = client.post("/data-sources/test", json={"kind": "sqlite", "connection_uri": uri}, headers=headers)
    assert test.status_code == 200
    assert test.json()["ok"] is True
    assert "margin_reports" in test.json()["tables"]

    connect = client.post("/data-sources", json={"kind": "sqlite", "connection_uri": uri, "name": "Broker DB"}, headers=headers).json()
    assert connect["status"] == "connected"

    imp = client.post(f"/data-sources/{connect['id']}/import", headers=headers, json={
        "table": "margin_reports", "description_column": "note",
        "captured_column": "captured", "metric_columns": ["pct"],
    }).json()
    assert imp["imported"] == 1
