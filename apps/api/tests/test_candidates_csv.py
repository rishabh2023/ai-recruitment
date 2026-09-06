"""Bulk candidate import from CSV: name + mobile mandatory, per-row error reporting, dedup."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE organizations RESTART IDENTITY CASCADE"))


def _job(client):
    client.post("/dev/bootstrap", json={"org_name": "Acme", "user_email": "r@acme.test", "password": "pw-123456"})
    client.post("/auth/login", json={"email": "r@acme.test", "password": "pw-123456"})
    return client.post("/jobs", json={"title": "Backend Engineer"}).json()["id"]


def _upload(client, jid, csv_text):
    return client.post(
        f"/jobs/{jid}/candidates/import-csv",
        files={"file": ("candidates.csv", csv_text.encode(), "text/csv")},
    )


def test_csv_imports_valid_rows_and_reports_bad_ones(client):
    jid = _job(client)
    csv_text = (
        "name,mobile,email,location\n"
        "Asha Rao,+919900112233,asha@x.com,Bengaluru\n"
        "Bo Li,+919900445566,,Pune\n"
        ",+919900778899,noname@x.com,\n"      # missing name
        "No Phone,,np@x.com,Delhi\n"          # missing mobile
    )
    r = _upload(client, jid, csv_text)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["added"] == 2
    assert body["skipped"] == 2
    reasons = {e["reason"] for e in body["errors"]}
    assert any("name" in x.lower() for x in reasons)
    assert any("mobile" in x.lower() for x in reasons)
    assert len(client.get(f"/jobs/{jid}/candidates").json()) == 2


def test_csv_accepts_header_aliases(client):
    jid = _job(client)
    # "Full Name" + "Phone Number" should be recognized.
    r = _upload(client, jid, "Full Name,Phone Number\nAsha Rao,+919900112233\n")
    assert r.status_code == 201, r.text
    assert r.json()["added"] == 1


def test_csv_dedupes_repeated_mobile(client):
    jid = _job(client)
    r = _upload(client, jid, "name,mobile\nAsha,+911111111111\nAsha Again,+911111111111\n")
    assert r.status_code == 201
    assert r.json()["added"] == 1 and r.json()["skipped"] == 1


def test_csv_bare_number_without_country_code_is_reported(client):
    jid = _job(client)
    r = _upload(client, jid, "name,mobile\nAsha,8965823672\n")
    assert r.status_code == 201
    body = r.json()
    assert body["added"] == 0 and body["skipped"] == 1
    assert "country code" in body["errors"][0]["reason"].lower()


def test_csv_country_code_column_builds_e164(client):
    jid = _job(client)
    r = _upload(client, jid, "name,mobile,country_code\nAsha,8965823672,+91\nBo,9876543210,91\n")
    assert r.status_code == 201, r.text
    assert r.json()["added"] == 2
    phones = {c["candidate"]["phone"] for c in client.get(f"/jobs/{jid}/candidates").json()}
    assert phones == {"+918965823672", "+919876543210"}


def test_csv_missing_required_columns_is_rejected(client):
    jid = _job(client)
    r = _upload(client, jid, "email,city\na@x.com,Pune\n")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_update_candidate_edits_profile(client):
    jid = _job(client)
    jc = client.post(f"/jobs/{jid}/candidates", json={"full_name": "Old Name", "phone": "8965823672"}).json()["id"]
    r = client.patch(f"/job-candidates/{jc}", json={"full_name": "New Name", "phone": "+918965823672", "location": "Pune"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "New Name" and body["phone"] == "+918965823672" and body["location"] == "Pune"
    # empty full_name is rejected
    assert client.patch(f"/job-candidates/{jc}", json={"full_name": "  "}).status_code == 422
    # clearing an optional field with empty string
    assert client.patch(f"/job-candidates/{jc}", json={"location": ""}).json()["location"] is None


def test_manual_add_rejects_duplicate_phone_in_job(client):
    jid = _job(client)
    r1 = client.post(f"/jobs/{jid}/candidates", json={"full_name": "Rishabh", "phone": "+918965823672"})
    assert r1.status_code == 201
    # same digits, different formatting → still a duplicate for this role
    r2 = client.post(f"/jobs/{jid}/candidates", json={"full_name": "Rishabh Again", "phone": "8965823672"})
    assert r2.status_code == 409
    assert "phone" in r2.json()["error"]["message"].lower()
    # a different number is fine
    assert client.post(f"/jobs/{jid}/candidates", json={"full_name": "Other", "phone": "+919000000000"}).status_code == 201


def test_manual_add_rejects_duplicate_email_in_job(client):
    jid = _job(client)
    client.post(f"/jobs/{jid}/candidates", json={"full_name": "A", "email": "a@x.com"})
    r = client.post(f"/jobs/{jid}/candidates", json={"full_name": "B", "email": "A@X.com"})
    assert r.status_code == 409 and "email" in r.json()["error"]["message"].lower()
