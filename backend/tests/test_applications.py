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
