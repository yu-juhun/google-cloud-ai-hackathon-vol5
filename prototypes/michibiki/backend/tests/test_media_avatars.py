from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from michibiki import db
from michibiki.media import client_hash
from michibiki.server import app
from sqlalchemy import create_engine
import pytest

client = TestClient(app)
HEADERS = {"X-Michibiki-Client": "a" * 40}


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    db.migrate(engine)
    yield engine
    engine.dispose()


def _catalog():
    return {"female": {"mood": [
        {"id": f"female_style_{i}", "title": f"Style {i}"} for i in range(12)
    ]}}


@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_create_avatars_picks_ten_unused_styles(mock_rpc, database):
    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": f"female_style_{i}", "task_id": f"task-{i}"} for i in range(10)]},
    ]
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["avatar_count"] == 10
    batch_call = mock_rpc.call_args_list[1]
    assert batch_call.args[0] == "/avatar-jobs-batch"
    chosen = batch_call.args[1]["template_ids"]
    assert len(chosen) == 10
    assert len(set(chosen)) == 10  # no duplicates
    assert all(t in {f"female_style_{i}" for i in range(12)} for t in chosen)


@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_create_avatars_avoids_already_used_styles_on_a_second_generation(mock_rpc, database):
    # Only 1 style used out of 12 (11 unused remain — above the 10-style wrap threshold,
    # so this exercises exclusion of used styles without also triggering a version wrap,
    # which is covered separately below).
    headers = {"X-Michibiki-Client": "x" * 40}
    db.add_avatar_pool_entries(client_hash(headers["X-Michibiki-Client"]), 1, [
        {"template_id": "female_style_0", "object_name": "avatars/prev/0"},
    ])
    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": f"female_style_{i}", "task_id": f"task-{i}"} for i in range(1, 11)]},
    ]
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=headers)
    assert response.status_code == 200
    chosen = mock_rpc.call_args_list[1].args[1]["template_ids"]
    assert len(chosen) == 10
    assert "female_style_0" not in chosen  # the already-used style is excluded


@patch("michibiki.media.storage.Client")
@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_create_avatars_wraps_to_a_new_version_when_fewer_than_ten_styles_remain(
    mock_rpc, mock_storage, database, monkeypatch,
):
    monkeypatch.setenv("AVATAR_BUCKET", "test-avatar-bucket")
    token = "y" * 64
    owner = client_hash(token)
    db.add_avatar_pool_entries(owner, 1, [
        {"template_id": f"female_style_{i}", "object_name": f"avatars/prev/{i}"} for i in range(8)
    ])  # only 4 styles unused (12 total - 8 used) — below the 10 threshold
    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": f"female_style_{i}", "task_id": f"task-{i}"} for i in range(10)]},
    ]
    headers = {"X-Michibiki-Client": token}
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=headers)
    assert response.status_code == 200
    assert db.get_avatar_pool(owner, 1) == []  # version 1 was deleted
    # get_current_avatar_version derives from avatar_pool rows, which are only written
    # once the generation job completes (GET /avatars/{set_id}) — not at creation time.
    # So right after POST we confirm the new set recorded version 2 directly.
    record = db.get_avatar_set(response.json()["id"], owner)
    assert record["version"] == 2
    chosen = mock_rpc.call_args_list[1].args[1]["template_ids"]
    assert len(set(chosen)) == 10  # full 12-style catalog was available again


@patch("michibiki.media.storage.Client")
@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_create_avatars_does_not_wrap_when_exactly_ten_styles_remain(mock_rpc, mock_storage, database):
    # 12-style catalog, 2 already used → exactly 10 unused remain. The spec's
    # wraparound only triggers on FEWER than 10, so this must NOT delete the pool.
    token = "u" * 64
    owner = client_hash(token)
    db.add_avatar_pool_entries(owner, 1, [
        {"template_id": "female_style_0", "object_name": "avatars/prev/0"},
        {"template_id": "female_style_1", "object_name": "avatars/prev/1"},
    ])
    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": f"female_style_{i}", "task_id": f"task-{i}"} for i in range(2, 12)]},
    ]
    headers = {"X-Michibiki-Client": token}
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=headers)
    assert response.status_code == 200
    assert db.get_current_avatar_version(owner) == 1  # did not wrap
    assert len(db.get_avatar_pool(owner, 1)) == 2  # old entries preserved, not deleted
    chosen = mock_rpc.call_args_list[1].args[1]["template_ids"]
    assert set(chosen) == {f"female_style_{i}" for i in range(2, 12)}


@patch("michibiki.media.storage.Client")
def test_pool_endpoint_returns_signed_urls_and_selected_avatar(mock_storage, database, monkeypatch):
    monkeypatch.setenv("AVATAR_BUCKET", "test-avatar-bucket")
    monkeypatch.setenv("AVATAR_SIGNER", "signer@example.com")
    token = "z" * 64
    owner = client_hash(token)
    db.add_avatar_pool_entries(owner, 1, [{"template_id": "female_style_0", "object_name": "avatars/a/0"}])
    db.set_profile_avatar(owner, "avatars/a/0")
    mock_bucket = mock_storage.return_value.bucket.return_value
    mock_bucket.blob.return_value.generate_signed_url.return_value = "https://signed.example/a0"
    with patch("michibiki.media.google.auth.default", return_value=(MagicMock(), None)):
        response = client.get("/api/avatars/pool", headers={"X-Michibiki-Client": token})
    assert response.status_code == 200
    body = response.json()
    assert body["avatars"][0]["url"] == "https://signed.example/a0"
    assert body["selected"] == "avatars/a/0"


def test_select_avatar_rejects_an_object_name_not_in_the_callers_pool(database):
    token = "w" * 64
    owner = client_hash(token)
    db.add_avatar_pool_entries(owner, 1, [{"template_id": "female_style_0", "object_name": "avatars/a/0"}])
    response = client.put("/api/profile/avatar", json={"object_name": "avatars/someone-else/9"},
                          headers={"X-Michibiki-Client": token})
    assert response.status_code == 404


def test_select_avatar_accepts_an_object_name_in_the_callers_pool(database):
    token = "v" * 64
    owner = client_hash(token)
    db.add_avatar_pool_entries(owner, 1, [{"template_id": "female_style_0", "object_name": "avatars/a/0"}])
    response = client.put("/api/profile/avatar", json={"object_name": "avatars/a/0"},
                          headers={"X-Michibiki-Client": token})
    assert response.status_code == 200
    assert db.get_profile_avatar(owner) == "avatars/a/0"


@patch("michibiki.media.storage.Client")
@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_wraparound_clears_the_stale_profile_avatar_selection(mock_rpc, mock_storage, database):
    """Regression test for I2: a profile that had selected an avatar from the
    old (version 1) pool must have that selection cleared when the pool wraps
    to version 2, so get()'s "default to first new avatar if none selected"
    logic actually re-fires instead of leaving the icon pointed at a deleted
    object."""
    token = "q" * 64
    owner = client_hash(token)
    db.add_avatar_pool_entries(owner, 1, [
        {"template_id": f"female_style_{i}", "object_name": f"avatars/prev/{i}"} for i in range(8)
    ])  # only 4 unused of 12 -> below the 10 threshold, triggers wraparound
    db.set_profile_avatar(owner, "avatars/prev/0")
    assert db.get_profile_avatar(owner) == "avatars/prev/0"

    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": f"female_style_{i}", "task_id": f"task-{i}"} for i in range(10)]},
    ]
    import os as _os
    _os.environ["AVATAR_BUCKET"] = "test-avatar-bucket"
    headers = {"X-Michibiki-Client": token}
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=headers)
    assert response.status_code == 200

    assert db.get_profile_avatar(owner) is None  # stale selection cleared on wraparound


@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_wraparound_batch_submit_failure_leaves_old_pool_intact(mock_rpc, database, monkeypatch):
    """Regression test for I3(a): if submitting the new batch to
    persona-agent-backend fails, the old pool (up to the deletion threshold)
    must still be there afterward -- the user must not lose their existing
    avatars without gaining replacements."""
    from fastapi import HTTPException

    monkeypatch.setenv("AVATAR_BUCKET", "test-avatar-bucket")
    token = "s" * 64
    owner = client_hash(token)
    db.add_avatar_pool_entries(owner, 1, [
        {"template_id": f"female_style_{i}", "object_name": f"avatars/prev/{i}"} for i in range(8)
    ])  # below the 10 threshold -> would wrap
    mock_rpc.side_effect = [_catalog(), HTTPException(503, "down")]
    headers = {"X-Michibiki-Client": token}
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=headers)
    assert response.status_code == 503
    assert len(db.get_avatar_pool(owner, 1)) == 8  # old pool untouched


@patch("michibiki.media.storage.Client")
@patch("michibiki.media.persona_rpc", new_callable=AsyncMock)
def test_wraparound_tolerates_a_missing_blob_during_pool_cleanup(mock_rpc, mock_storage, database, monkeypatch):
    """Regression test for I3(b): a NotFound raised by one blob's delete() during
    wraparound cleanup must not propagate as an unhandled exception / 500."""
    from google.api_core.exceptions import NotFound

    monkeypatch.setenv("AVATAR_BUCKET", "test-avatar-bucket")
    token = "r" * 64
    owner = client_hash(token)
    db.add_avatar_pool_entries(owner, 1, [
        {"template_id": f"female_style_{i}", "object_name": f"avatars/prev/{i}"} for i in range(8)
    ])
    mock_blob = mock_storage.return_value.bucket.return_value.blob.return_value
    mock_blob.delete.side_effect = NotFound("gone")
    mock_rpc.side_effect = [
        _catalog(),
        {"tasks": [{"template_id": f"female_style_{i}", "task_id": f"task-{i}"} for i in range(10)]},
    ]
    headers = {"X-Michibiki-Client": token}
    response = client.post("/api/avatars", json={"photo": "ZmFrZQ==", "consent": True}, headers=headers)
    assert response.status_code == 200
    assert db.get_avatar_pool(owner, 1) == []  # cleanup still completed despite the missing blob
