"""API tests for the add-by-link application flow (isolated in-memory DB)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes import router
from app.db import get_session


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c


PAYLOAD = {
    "url": "https://boards.greenhouse.io/acme/jobs/123",
    "title": "Graduate Software Engineer",
    "company": "Acme",
}


def test_add_by_link_creates_saved_application(client):
    r = client.post("/applications", json=PAYLOAD)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "interested"          # "Saved" stage
    assert data["applied_at"] is None
    assert data["job"]["title"] == "Graduate Software Engineer"
    assert data["job"]["company_name"] == "Acme"
    assert data["job"]["apply_url"] == PAYLOAD["url"]

    # The company was auto-created and is listed.
    companies = client.get("/companies").json()
    assert any(c["name"] == "Acme" for c in companies)


def test_move_to_applied_stamps_date(client):
    app_id = client.post("/applications", json=PAYLOAD).json()["id"]
    r = client.patch(f"/applications/{app_id}", json={"status": "applied"})
    assert r.status_code == 200, r.text
    assert r.json()["applied_at"] is not None


def test_duplicate_url_conflicts(client):
    assert client.post("/applications", json=PAYLOAD).status_code == 200
    dup = client.post("/applications", json=PAYLOAD)
    assert dup.status_code == 409


def test_delete_removes_application(client):
    app_id = client.post("/applications", json=PAYLOAD).json()["id"]
    assert client.delete(f"/applications/{app_id}").status_code == 204
    assert client.get("/applications").json() == []


# --- detail-view editing --------------------------------------------------------------

def test_applied_at_can_be_backdated(client):
    app_id = client.post("/applications", json=PAYLOAD).json()["id"]
    r = client.patch(
        f"/applications/{app_id}",
        json={"status": "applied", "applied_at": "2026-08-01T09:00:00Z"},
    )
    assert r.status_code == 200, r.text
    # The explicit date must survive the auto-stamp that fires on the same transition.
    assert r.json()["applied_at"].startswith("2026-08-01T09:00:00")


def test_editing_job_fields_from_detail_view(client):
    app_id = client.post("/applications", json=PAYLOAD).json()["id"]
    r = client.patch(
        f"/applications/{app_id}",
        json={
            "title": "Senior Software Engineer",
            "apply_url": "https://boards.greenhouse.io/acme/jobs/999",
            "sector": "finance",
        },
    )
    assert r.status_code == 200, r.text
    job = r.json()["job"]
    assert job["title"] == "Senior Software Engineer"
    assert job["apply_url"] == "https://boards.greenhouse.io/acme/jobs/999"
    assert job["sector"] == "finance"


def test_renaming_company_from_detail_view_corrects_in_place(client):
    """Fixing a mis-parsed name ("Goldman Sach") on the only job at that company is a
    correction: rename the row, keep its domains, and leave no orphan behind. An orphan
    would still match the domain in the poller while owning no application, so a
    confirmation email would stop auto-confirming."""
    created = client.post(
        "/applications", json={**PAYLOAD, "company": "Acme", "email_domains": "acme.com"}
    ).json()
    old_company_id = created["job"]["company_id"]

    r = client.patch(
        f"/applications/{created['id']}",
        json={"company": "Acme Corp", "email_domains": "acme.com"},
    )
    assert r.status_code == 200, r.text
    job = r.json()["job"]
    assert job["company_name"] == "Acme Corp"
    assert job["company_id"] == old_company_id      # renamed in place, not duplicated
    assert job["company_email_domains"] == "acme.com"
    assert [c["name"] for c in client.get("/companies").json()] == ["Acme Corp"]


def test_moving_a_job_to_an_existing_company_reuses_it(client):
    client.post("/companies", json={"name": "Beta Corp", "email_domains": "beta.com"})
    created = client.post("/applications", json=PAYLOAD).json()

    r = client.patch(f"/applications/{created['id']}", json={"company": "Beta Corp"})
    assert r.status_code == 200, r.text
    assert r.json()["job"]["company_email_domains"] == "beta.com"
    names = sorted(c["name"] for c in client.get("/companies").json())
    assert names == ["Acme", "Beta Corp"]           # reused, not a third row


def test_company_rename_updates_slug_so_later_adds_reuse_it(client):
    """The slug drives find-or-create. Leaving it stale made the next job at the same
    employer create a duplicate company with no domains."""
    client.post(
        "/applications",
        json={**PAYLOAD, "company": "Goldman Sach", "email_domains": "gs.com"},
    )
    cid = client.get("/companies").json()[0]["id"]
    assert client.patch(f"/companies/{cid}", json={"name": "Goldman Sachs"}).status_code == 200

    client.post("/applications", json={
        "url": "https://higher.gs.com/roles/2", "title": "Associate",
        "company": "Goldman Sachs",
    })
    companies = client.get("/companies").json()
    assert len(companies) == 1, companies
    assert companies[0]["slug"] == "goldman-sachs"
    assert companies[0]["email_domains"] == "gs.com"


def test_company_rename_onto_an_existing_name_conflicts(client):
    a = client.post("/companies", json={"name": "Acme"}).json()
    client.post("/companies", json={"name": "Beta"})
    assert client.patch(f"/companies/{a['id']}", json={"name": "Beta"}).status_code == 409


def test_company_name_patch_leaves_domains_alone(client):
    company = client.post(
        "/companies", json={"name": "Goldman Sach", "email_domains": "gs.com,oracle.com"}
    ).json()
    r = client.patch(f"/companies/{company['id']}", json={"name": "Goldman Sachs"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Goldman Sachs"
    assert r.json()["email_domains"] == "gs.com,oracle.com"


def test_editing_email_domains_overwrites_existing(client):
    """Add-by-link only backfills empty domains; an explicit edit must be able to correct."""
    created = client.post(
        "/applications", json={**PAYLOAD, "email_domains": "wrong.com"}
    ).json()
    assert created["job"]["company_email_domains"] == "wrong.com"

    r = client.patch(
        f"/applications/{created['id']}", json={"email_domains": "acme.com, acme.com.sg"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["job"]["company_email_domains"] == "acme.com, acme.com.sg"


def test_company_patch_preserves_unsent_fields(client):
    """Regression: PATCH used to take a full body and wipe notes/sector/career_page_url."""
    company = client.post(
        "/companies",
        json={
            "name": "Acme",
            "email_domains": "acme.com",
            "career_page_url": "https://acme.com/careers",
            "sector": "finance",
            "notes": "referral via Sam",
        },
    ).json()

    r = client.patch(f"/companies/{company['id']}", json={"email_domains": "acme.com.sg"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["email_domains"] == "acme.com.sg"
    assert data["notes"] == "referral via Sam"
    assert data["sector"] == "finance"
    assert data["career_page_url"] == "https://acme.com/careers"
