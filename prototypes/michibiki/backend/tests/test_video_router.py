from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from michibiki.server import app

client = TestClient(app)
HEADERS = {"X-Michibiki-Client": "a" * 40}


def _report_row():
    return {
        "id": "report-1",
        "body": {
            "assignment": {"goal": "商店街を車椅子で巡る"},
            "assessments": [{"experience": "入口は段差なし", "fit_reason": "問題なし"}],
        },
    }


def _avatar_row():
    return {
        "id": "avatar-1",
        "status": "ready",
        "assets": {"assets": [{"object_name": "avatars/avatar-1/0.png"}]},
    }


@patch("michibiki.video._download_avatar_image", return_value=b"fake-image-bytes")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_latest_ready_avatar_set")
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.get_report")  # see Step 3 note: this function is new, added in this task
def test_create_video_job_success(
    mock_get_report, mock_find_active, mock_update, mock_find_avatar, mock_create,
    mock_guard, mock_rpc, mock_download,
):
    mock_get_report.return_value = _report_row()
    mock_find_avatar.return_value = _avatar_row()
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.return_value = {"operation_name": "operations/abc123"}

    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
        "tone": "calm", "consent": True,
    }, headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {"id": "job-1", "status": "queued"}
    mock_create.assert_called_once()
    mock_rpc.assert_awaited_once()
    assert mock_rpc.await_args.args[0] == "/video-jobs"
    body = mock_rpc.await_args.args[1]
    assert body["report_text"] == "入口は段差なし"
    assert body["mobility_notes"] == ""
    assert body["feedback"] == "もっと明るく"
    assert body["style"] == "cinematic"
    assert body["tone"] == "calm"
    assert body["image_mime_type"] == "image/png"
    mock_update.assert_called_once_with("job-1", "queued", provider_operation_name="operations/abc123")


def test_create_video_job_rejects_missing_consent():
    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "x", "style": "cinematic", "tone": "calm", "consent": False,
    }, headers=HEADERS)
    assert response.status_code == 400


@patch("michibiki.db.find_active_video_job", return_value={"id": "existing-job"})
@patch("michibiki.db.get_report", return_value=_report_row())
def test_create_video_job_rejects_duplicate_in_flight(mock_get_report, mock_find_active):
    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "x", "style": "cinematic", "tone": "calm", "consent": True,
    }, headers=HEADERS)
    assert response.status_code == 409


@patch("michibiki.video.check_relevance", return_value=(False, "体験談と無関係です"))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.get_report", return_value=_report_row())
def test_create_video_job_rejects_off_topic_feedback_without_creating_a_row(
    mock_get_report, mock_find_active, mock_create, mock_guard,
):
    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "全く違う話題", "style": "cinematic", "tone": "calm", "consent": True,
    }, headers=HEADERS)
    assert response.status_code == 400
    assert "無関係" in response.json()["detail"]
    mock_create.assert_not_called()


def test_create_video_job_rejects_feedback_over_500_chars():
    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "x" * 501, "style": "cinematic", "tone": "calm", "consent": True,
    }, headers=HEADERS)
    assert response.status_code == 422  # pydantic max_length violation


@patch("michibiki.db.get_report", return_value=None)
def test_create_video_job_404s_on_unknown_report(mock_get_report):
    response = client.post("/api/videos", json={
        "report_id": "does-not-exist", "feedback": "x", "style": "cinematic", "tone": "calm", "consent": True,
    }, headers=HEADERS)
    assert response.status_code == 404


@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_latest_ready_avatar_set", return_value=None)
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.get_report", return_value=_report_row())
def test_create_video_job_404s_when_no_ready_avatar_set(
    mock_get_report, mock_find_active, mock_find_avatar, mock_create, mock_guard,
):
    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic", "tone": "calm", "consent": True,
    }, headers=HEADERS)
    assert response.status_code == 404
    assert "アバター" in response.json()["detail"]
    mock_create.assert_not_called()
