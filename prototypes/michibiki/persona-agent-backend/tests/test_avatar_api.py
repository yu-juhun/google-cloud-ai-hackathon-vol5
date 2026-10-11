import base64
import io
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from main import app

client = TestClient(app)


def _fake_photo_b64():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@patch("avatar_api.capabilities", return_value={"avatar_configured": True, "avatar_count": 10, "voice_model": "x"})
@patch("avatar_api.start_avatar_task")
@patch("avatar_api.flatten_template_ids", return_value={"female_manga_mood", "male_cool_mood", "female_sport_mood"})
@patch("avatar_api.load_avatar_template_catalog", return_value={})
def test_avatar_jobs_batch_submits_one_task_per_template(
    mock_catalog, mock_flatten, mock_start, mock_caps,
):
    mock_start.side_effect = ["task-1", "task-2"]
    response = client.post("/avatar-jobs-batch", json={
        "photo": _fake_photo_b64(), "consent": True,
        "template_ids": ["female_manga_mood", "male_cool_mood"],
    })
    assert response.status_code == 200
    assert response.json() == {"tasks": [
        {"template_id": "female_manga_mood", "task_id": "task-1"},
        {"template_id": "male_cool_mood", "task_id": "task-2"},
    ]}
    assert mock_start.call_count == 2
    for call in mock_start.call_args_list:
        assert call.args[3] == 1  # output_count=1 per template


@patch("avatar_api.capabilities", return_value={"avatar_configured": True, "avatar_count": 10, "voice_model": "x"})
@patch("avatar_api.flatten_template_ids", return_value={"female_manga_mood"})
@patch("avatar_api.load_avatar_template_catalog", return_value={})
def test_avatar_jobs_batch_rejects_an_unknown_template_id(mock_catalog, mock_flatten, mock_caps):
    response = client.post("/avatar-jobs-batch", json={
        "photo": _fake_photo_b64(), "consent": True,
        "template_ids": ["female_manga_mood", "not-a-real-style"],
    })
    assert response.status_code == 400


def test_avatar_jobs_batch_rejects_missing_consent():
    response = client.post("/avatar-jobs-batch", json={
        "photo": _fake_photo_b64(), "consent": False, "template_ids": ["female_manga_mood"],
    })
    assert response.status_code == 400


@patch("avatar_api.download_avatar", return_value=(b"fake-bytes", "image/jpeg"))
@patch("avatar_api.avatar_task_status")
@patch("avatar_api.storage.Client")
def test_avatar_results_batch_returns_generating_when_any_task_is_pending(
    mock_storage_client, mock_status, mock_download, monkeypatch,
):
    monkeypatch.setenv("AVATAR_BUCKET", "fake-bucket")
    mock_status.side_effect = [("success", [{"url": "https://example.com/a.jpg"}]), ("running", [])]
    mock_download.return_value = (_fake_photo_bytes(), "image/png")
    response = client.post("/avatar-results-batch", json={
        "tasks": [
            {"template_id": "female_manga_mood", "task_id": "task-1"},
            {"template_id": "male_cool_mood", "task_id": "task-2"},
        ],
        "set_id": "11111111-1111-1111-1111-111111111111",
    })
    assert response.status_code == 200
    assert response.json() == {"status": "generating", "done": 1, "total": 2}


@patch("avatar_api.download_avatar")
@patch("avatar_api.avatar_task_status")
@patch("avatar_api.storage.Client")
def test_avatar_results_batch_skips_a_failed_template_and_returns_the_rest(
    mock_storage_client, mock_status, mock_download, monkeypatch,
):
    monkeypatch.setenv("AVATAR_BUCKET", "fake-bucket")
    mock_status.side_effect = [("error", []), ("success", [{"url": "https://example.com/b.jpg"}])]
    mock_download.return_value = (_fake_photo_bytes(), "image/png")
    response = client.post("/avatar-results-batch", json={
        "tasks": [
            {"template_id": "female_manga_mood", "task_id": "task-1"},
            {"template_id": "male_cool_mood", "task_id": "task-2"},
        ],
        "set_id": "11111111-1111-1111-1111-111111111111",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert len(body["avatars"]) == 1
    assert body["avatars"][0]["template_id"] == "male_cool_mood"


def _fake_photo_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    return buf.getvalue()


@patch("avatar_api.download_avatar", return_value=(b"not-a-real-image", "image/jpeg"))
@patch("avatar_api.avatar_task_status", return_value=("success", [{"url": "https://example.com/c.jpg"}]))
@patch("avatar_api.storage.Client")
def test_avatar_results_batch_skips_a_template_whose_download_is_corrupt(
    mock_storage_client, mock_status, mock_download, monkeypatch,
):
    monkeypatch.setenv("AVATAR_BUCKET", "fake-bucket")
    response = client.post("/avatar-results-batch", json={
        "tasks": [{"template_id": "female_manga_mood", "task_id": "task-1"}],
        "set_id": "11111111-1111-1111-1111-111111111111",
    })
    assert response.status_code == 200
    assert response.json() == {"status": "failed"}  # the one template failed verify(), nothing ready


@patch("avatar_api.avatar_task_status", return_value=("error", []))
def test_avatar_results_batch_returns_failed_when_every_task_failed(mock_status, monkeypatch):
    monkeypatch.setenv("AVATAR_BUCKET", "fake-bucket")
    response = client.post("/avatar-results-batch", json={
        "tasks": [{"template_id": "female_manga_mood", "task_id": "task-1"}],
        "set_id": "11111111-1111-1111-1111-111111111111",
    })
    assert response.status_code == 200
    assert response.json() == {"status": "failed"}
