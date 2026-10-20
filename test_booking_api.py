"""
API Testing with Requests + Pytest (single-file example)
Target API: https://restful-booker.herokuapp.com (public API built for test practice)

SETUP
    pip install requests pytest jsonschema

RUN
    pytest test_booking_api.py -v
    pytest test_booking_api.py -v -k "auth"      # run a subset
    BASE_URL=https://your-own-host pytest ...    # override target

COVERS
    - Health check and auth (positive + negative)
    - Full CRUD lifecycle: create, read, update (PUT), partial update (PATCH), delete
    - Authorization checks (requests without a token)
    - JSON schema validation
    - Response time and header checks
    - Parametrized data-driven tests
    - Fixtures that create and clean up their own test data

NOTE
    The demo server is shared and occasionally resets or is slow.
    If a test fails with a timeout, just re-run.
"""

import os
import time

import pytest
import requests
from jsonschema import validate

BASE_URL = os.getenv("BASE_URL", "https://restful-booker.herokuapp.com")
TIMEOUT = 15
USERNAME = "admin"
PASSWORD = "password123"

BOOKING_SCHEMA = {
    "type": "object",
    "required": ["firstname", "lastname", "totalprice", "depositpaid", "bookingdates"],
    "properties": {
        "firstname": {"type": "string"},
        "lastname": {"type": "string"},
        "totalprice": {"type": "number"},
        "depositpaid": {"type": "boolean"},
        "bookingdates": {
            "type": "object",
            "required": ["checkin", "checkout"],
            "properties": {
                "checkin": {"type": "string"},
                "checkout": {"type": "string"},
            },
        },
        "additionalneeds": {"type": "string"},
    },
}


# --------------------------------------------------------------------------
# Helpers and fixtures
# --------------------------------------------------------------------------
def make_booking(**overrides):
    """Build a valid booking payload; override any field via kwargs."""
    payload = {
        "firstname": "Jane",
        "lastname": "Tester",
        "totalprice": 250,
        "depositpaid": True,
        "bookingdates": {"checkin": "2026-12-01", "checkout": "2026-12-05"},
        "additionalneeds": "Breakfast",
    }
    payload.update(overrides)
    return payload


class ApiClient(requests.Session):
    """requests.Session that prefixes the base URL and applies a default timeout."""

    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", TIMEOUT)
        return super().request(method, f"{self.base_url}{url}", **kwargs)


@pytest.fixture(scope="session")
def client():
    return ApiClient(BASE_URL)


@pytest.fixture(scope="session")
def token(client):
    resp = client.post("/auth", json={"username": USERNAME, "password": PASSWORD})
    assert resp.status_code == 200
    value = resp.json().get("token")
    assert value, "Auth did not return a token"
    return value


@pytest.fixture
def auth_headers(token):
    return {"Cookie": f"token={token}"}


@pytest.fixture
def booking(client, auth_headers):
    """Create a booking for a test, then delete it afterwards."""
    resp = client.post("/booking", json=make_booking())
    assert resp.status_code == 200
    data = resp.json()
    yield data  # {"bookingid": ..., "booking": {...}}
    client.delete(f"/booking/{data['bookingid']}", headers=auth_headers)


# --------------------------------------------------------------------------
# Health check
# --------------------------------------------------------------------------
def test_health_check(client):
    resp = client.get("/ping")
    assert resp.status_code == 201  # this API returns 201 Created for /ping


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
def test_auth_returns_token(client):
    resp = client.post("/auth", json={"username": USERNAME, "password": PASSWORD})
    assert resp.status_code == 200
    assert isinstance(resp.json()["token"], str)
    assert len(resp.json()["token"]) > 5


@pytest.mark.parametrize(
    "username, password",
    [
        (USERNAME, "wrong-password"),
        ("not-a-user", PASSWORD),
        ("", ""),
    ],
    ids=["bad-password", "bad-username", "empty-credentials"],
)
def test_auth_rejects_bad_credentials(client, username, password):
    resp = client.post("/auth", json={"username": username, "password": password})
    # This API signals failure in the body instead of using a 401
    assert "token" not in resp.json()
    assert resp.json().get("reason") == "Bad credentials"


# --------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------
def test_get_all_bookings_returns_ids(client):
    resp = client.get("/booking")
    assert resp.status_code == 200
    bookings = resp.json()
    assert isinstance(bookings, list) and len(bookings) > 0
    assert all("bookingid" in b for b in bookings[:20])


def test_get_booking_matches_schema(client, booking):
    resp = client.get(f"/booking/{booking['bookingid']}")
    assert resp.status_code == 200
    validate(instance=resp.json(), schema=BOOKING_SCHEMA)


def test_get_nonexistent_booking_returns_404(client):
    resp = client.get("/booking/99999999")
    assert resp.status_code == 404


def test_filter_bookings_by_name(client, booking):
    resp = client.get("/booking", params={"firstname": "Jane", "lastname": "Tester"})
    assert resp.status_code == 200
    ids = [b["bookingid"] for b in resp.json()]
    assert booking["bookingid"] in ids


# --------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------
def test_create_booking_returns_what_was_sent(client, auth_headers):
    payload = make_booking(firstname="Alex", lastname="Rivera", totalprice=480)
    resp = client.post("/booking", json=payload)
    assert resp.status_code == 200

    body = resp.json()
    assert isinstance(body["bookingid"], int)
    assert body["booking"] == payload
    validate(instance=body["booking"], schema=BOOKING_SCHEMA)

    client.delete(f"/booking/{body['bookingid']}", headers=auth_headers)  # cleanup


@pytest.mark.parametrize(
    "firstname, totalprice",
    [("Ana", 0), ("Bob", 1), ("Zoë", 99999), ("O'Brien", 150)],
    ids=["zero-price", "min-price", "large-price", "apostrophe-name"],
)
def test_create_booking_data_driven(client, auth_headers, firstname, totalprice):
    resp = client.post("/booking", json=make_booking(firstname=firstname, totalprice=totalprice))
    assert resp.status_code == 200
    created = resp.json()
    assert created["booking"]["firstname"] == firstname
    assert created["booking"]["totalprice"] == totalprice
    client.delete(f"/booking/{created['bookingid']}", headers=auth_headers)


# --------------------------------------------------------------------------
# Update
# --------------------------------------------------------------------------
def test_put_replaces_booking(client, booking, auth_headers):
    new_data = make_booking(firstname="Updated", lastname="Person", totalprice=999)
    resp = client.put(f"/booking/{booking['bookingid']}", json=new_data, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == new_data

    # Verify the change persisted
    fetched = client.get(f"/booking/{booking['bookingid']}").json()
    assert fetched["firstname"] == "Updated"


def test_patch_updates_only_given_fields(client, booking, auth_headers):
    resp = client.patch(
        f"/booking/{booking['bookingid']}",
        json={"firstname": "Patched"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["firstname"] == "Patched"
    assert body["lastname"] == booking["booking"]["lastname"]  # unchanged


def test_update_without_token_is_forbidden(client, booking):
    resp = client.put(f"/booking/{booking['bookingid']}", json=make_booking())
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# Delete
# --------------------------------------------------------------------------
def test_delete_booking(client, auth_headers):
    created = client.post("/booking", json=make_booking()).json()
    booking_id = created["bookingid"]

    resp = client.delete(f"/booking/{booking_id}", headers=auth_headers)
    assert resp.status_code == 201  # this API returns 201 Created on delete

    assert client.get(f"/booking/{booking_id}").status_code == 404


def test_delete_without_token_is_forbidden(client, booking):
    resp = client.delete(f"/booking/{booking['bookingid']}")
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# Non-functional checks
# --------------------------------------------------------------------------
def test_response_headers(client):
    resp = client.get("/booking")
    assert "application/json" in resp.headers["Content-Type"]


def test_response_time_under_threshold(client):
    start = time.perf_counter()
    resp = client.get("/booking")
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert elapsed < 5, f"Response took {elapsed:.2f}s"


def test_full_crud_lifecycle(client, auth_headers):
    """One end-to-end scenario: create, read, update, delete, confirm gone."""
    created = client.post("/booking", json=make_booking(firstname="Lifecycle"))
    assert created.status_code == 200
    booking_id = created.json()["bookingid"]

    assert client.get(f"/booking/{booking_id}").json()["firstname"] == "Lifecycle"

    updated = client.put(
        f"/booking/{booking_id}",
        json=make_booking(firstname="Lifecycle2"),
        headers=auth_headers,
    )
    assert updated.json()["firstname"] == "Lifecycle2"

    assert client.delete(f"/booking/{booking_id}", headers=auth_headers).status_code == 201
    assert client.get(f"/booking/{booking_id}").status_code == 404
