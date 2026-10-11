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
