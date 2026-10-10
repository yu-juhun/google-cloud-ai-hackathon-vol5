import base64
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_video_job_calls_start_video_task():
    with patch("main.start_video_task", return_value="operations/abc123") as mock_start:
        response = client.post("/video-jobs", json={
            "image_bytes_b64": base64.b64encode(b"fake-image").decode("ascii"),
            "image_mime_type": "image/png",
            "report_text": "入口は段差なし",
            "feedback": "もっと明るく",
            "style": "cinematic",
            "tone": "calm",
        })
    assert response.status_code == 200
    assert response.json() == {"operation_name": "operations/abc123"}
    mock_start.assert_called_once()
    assert mock_start.call_args.args[0] == b"fake-image"


def test_get_video_job_status_ready_returns_base64_video():
    with patch("main.video_task_status", return_value=("ready", b"fake-video-bytes", "video/mp4")):
        response = client.get("/video-jobs/operations%2Fabc123/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert base64.b64decode(body["video_bytes_b64"]) == b"fake-video-bytes"


def test_get_video_job_status_generating_returns_no_video():
    with patch("main.video_task_status", return_value=("generating", None, None)):
        response = client.get("/video-jobs/operations%2Fabc123/status")
    assert response.json() == {"status": "generating", "video_bytes_b64": None, "mime_type": None}
