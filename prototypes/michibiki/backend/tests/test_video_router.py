from unittest.mock import AsyncMock, patch
import pytest

from fastapi.testclient import TestClient

from michibiki.server import app

client = TestClient(app)
HEADERS = {"X-Michibiki-Client": "a" * 40}


@pytest.fixture(autouse=True)
def scene_context():
    with patch("michibiki.db.get_report_scene_context", return_value={}):
        yield


def _report_row():
    return {
        "id": "report-1",
        "body": {
            "assignment": {"goal": "商店街を車椅子で巡る"},
            "assessments": [{"experience": "入口は段差なし", "fit_reason": "問題なし"}],
        },
    }


def _avatar_row(mime_type=None):
    asset = {"object_name": "avatars/avatar-1/0.png"}
    if mime_type:
        asset["mime_type"] = mime_type
    return {
        "id": "avatar-1",
        "status": "ready",
        "assets": {"assets": [asset]},
    }


def _report_row_with_experience_image(status="ready"):
    row = _report_row()
    row["body"]["experience_image"] = {
        "status": status, "object_name": "experiences/mission-1/twin-1.image",
        "place_id": "place-1", "scene_kind": "experience",
    }
    return row


@patch("michibiki.db.get_mission_profile", return_value=None)
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
    mock_guard, mock_rpc, mock_download, mock_profile,
):
    mock_get_report.return_value = _report_row()
    mock_find_avatar.return_value = _avatar_row(mime_type="image/jpeg")
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
    assert body["image_mime_type"] == "image/jpeg"  # uses the real avatar asset mime type
    mock_update.assert_called_once_with("job-1", "queued", provider_operation_name="operations/abc123")


@patch("michibiki.db.get_mission_profile", return_value=None)
@patch("michibiki.video._download_experience_image", return_value=b"fake-scene-bytes")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.get_report")
def test_create_video_job_prefers_ready_experience_image_over_avatar(
    mock_get_report, mock_update, mock_find_active, mock_create, mock_guard, mock_rpc, mock_download, mock_profile,
):
    mock_get_report.return_value = _report_row_with_experience_image(status="ready")
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.return_value = {"operation_name": "operations/abc123"}

    with patch("michibiki.db.find_latest_ready_avatar_set") as mock_find_avatar:
        response = client.post("/api/videos", json={
            "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
            "tone": "calm", "consent": True,
        }, headers=HEADERS)

    assert response.status_code == 200
    mock_download.assert_called_once_with(mock_get_report.return_value["body"]["experience_image"])
    mock_find_avatar.assert_not_called()
    body = mock_rpc.await_args.args[1]
    assert body["image_mime_type"] == "image/png"


@patch("michibiki.db.get_mission_profile", return_value=None)
@patch("michibiki.video._download_avatar_image", return_value=b"fake-avatar-bytes")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_latest_ready_avatar_set")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.get_report")
def test_create_video_job_falls_back_to_avatar_when_experience_image_not_ready(
    mock_get_report, mock_update, mock_find_active, mock_find_avatar, mock_create, mock_guard, mock_rpc, mock_download, mock_profile,
):
    mock_get_report.return_value = _report_row_with_experience_image(status="generating")
    mock_find_avatar.return_value = _avatar_row(mime_type="image/jpeg")
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.return_value = {"operation_name": "operations/abc123"}

    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
        "tone": "calm", "consent": True,
    }, headers=HEADERS)

    assert response.status_code == 200
    mock_download.assert_called_once()
    body = mock_rpc.await_args.args[1]
    assert body["image_mime_type"] == "image/jpeg"


@patch("michibiki.db.get_mission_profile", return_value=None)
@patch("michibiki.video._download_avatar_image", return_value=b"fake-avatar-bytes")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_latest_ready_avatar_set")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.get_report")
def test_create_video_job_falls_back_to_avatar_when_experience_image_key_absent(
    mock_get_report, mock_update, mock_find_active, mock_find_avatar, mock_create, mock_guard, mock_rpc, mock_download, mock_profile,
):
    mock_get_report.return_value = _report_row()  # no experience_image key at all
    mock_find_avatar.return_value = _avatar_row(mime_type="image/png")
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.return_value = {"operation_name": "operations/abc123"}

    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
        "tone": "calm", "consent": True,
    }, headers=HEADERS)

    assert response.status_code == 200
    mock_download.assert_called_once()


@patch("michibiki.db.get_mission_profile")
@patch("michibiki.video._download_avatar_image", return_value=b"fake-image-bytes")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_latest_ready_avatar_set")
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.get_report")
def test_create_video_job_populates_mobility_notes_from_profile(
    mock_get_report, mock_find_active, mock_update, mock_find_avatar, mock_create,
    mock_guard, mock_rpc, mock_download, mock_profile,
):
    mock_get_report.return_value = _report_row()
    mock_find_avatar.return_value = _avatar_row()
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.return_value = {"operation_name": "operations/abc123"}
    mock_profile.return_value = {"chair": "手動車いす", "width": 70, "step": 2}

    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
        "tone": "calm", "consent": True,
    }, headers=HEADERS)

    assert response.status_code == 200
    body = mock_rpc.await_args.args[1]
    assert body["mobility_notes"] == "車いす種別: 手動車いす、横幅: 70cm、通行可能な段差: 2cm"


@patch("michibiki.db.get_mission_profile", return_value=None)
@patch("michibiki.video._download_avatar_image", return_value=b"fake-image-bytes")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.video.check_relevance", return_value=(True, ""))
@patch("michibiki.db.create_video_job")
@patch("michibiki.db.find_latest_ready_avatar_set")
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.get_report")
def test_create_video_job_marks_row_failed_when_video_rpc_raises(
    mock_get_report, mock_find_active, mock_update, mock_find_avatar, mock_create,
    mock_guard, mock_rpc, mock_download, mock_profile,
):
    from fastapi import HTTPException

    mock_get_report.return_value = _report_row()
    mock_find_avatar.return_value = _avatar_row()
    mock_create.return_value = {"id": "job-1", "status": "queued"}
    mock_rpc.side_effect = HTTPException(503, "動画生成APIに接続できませんでした。")

    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
        "tone": "calm", "consent": True,
    }, headers=HEADERS)

    assert response.status_code == 503
    mock_update.assert_called_once_with("job-1", "failed")


@patch("michibiki.video._genai_client")
@patch("michibiki.video.check_relevance")
@patch("michibiki.db.find_active_video_job", return_value=None)
@patch("michibiki.db.get_report", return_value=_report_row())
def test_create_video_job_503s_when_gemini_relevance_guard_errors(
    mock_get_report, mock_find_active, mock_guard, mock_client,
):
    from google.genai import errors as genai_errors

    mock_guard.side_effect = genai_errors.APIError(503, {"message": "boom"})

    response = client.post("/api/videos", json={
        "report_id": "report-1", "feedback": "もっと明るく", "style": "cinematic",
        "tone": "calm", "consent": True,
    }, headers=HEADERS)

    assert response.status_code == 503


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


HELLO = {"type": "hello", "client_token": "a" * 40}


@patch("michibiki.video._sign_video_url", return_value="https://signed.example/video.mp4")
@patch("michibiki.video._upload_video")
@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.get_video_job")
def test_progress_ws_sends_ready_status_and_closes(mock_get_job, mock_update_job, mock_rpc, mock_upload, mock_sign):
    mock_get_job.return_value = {"id": "job-1", "client_hash": "x", "status": "generating",
                                 "provider_operation_name": "operations/abc123"}
    mock_rpc.return_value = {"status": "ready", "video_bytes_b64": "Zm9v", "mime_type": "video/mp4"}

    with patch("michibiki.video.client_hash", return_value="x"):
        with client.websocket_connect("/api/video-jobs/job-1/progress", headers={"origin": "http://localhost:5173"}) as websocket:
            websocket.send_json(HELLO)
            first = websocket.receive_json()
            assert first["type"] == "status"
            assert first["status"] == "generating"
            second = websocket.receive_json()
            assert second["type"] == "status"
            assert second["status"] == "ready"
            assert "video_url" in second


@patch("michibiki.db.get_video_job", return_value=None)
def test_progress_ws_closes_immediately_for_unknown_job(mock_get_job):
    with client.websocket_connect("/api/video-jobs/does-not-exist/progress", headers={"origin": "http://localhost:5173"}) as websocket:
        import pytest
        from starlette.websockets import WebSocketDisconnect
        websocket.send_json(HELLO)
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_progress_ws_closes_for_missing_or_invalid_token():
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with client.websocket_connect("/api/video-jobs/job-1/progress", headers={"origin": "http://localhost:5173"}) as websocket:
        websocket.send_json({"type": "hello", "client_token": "too-short"})
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_progress_ws_rejects_origin_mismatch(monkeypatch):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setenv("FRONTEND_ORIGIN", "https://allowed.example")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/video-jobs/job-1/progress", headers={"origin": "https://evil.example"},
        ) as websocket:
            websocket.receive_json()


@patch("michibiki.video._sign_video_url", return_value="https://signed.example/video.mp4")
@patch("michibiki.db.get_video_job")
def test_progress_ws_accepts_matching_origin(mock_get_job, mock_sign, monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://allowed.example")
    mock_get_job.return_value = {"id": "job-1", "client_hash": "x", "status": "ready",
                                 "object_name": "videos/job-1"}
    with patch("michibiki.video.client_hash", return_value="x"):
        with client.websocket_connect(
            "/api/video-jobs/job-1/progress", headers={"origin": "https://allowed.example"},
        ) as websocket:
            websocket.send_json(HELLO)
            message = websocket.receive_json()
            assert message["status"] == "ready"


@patch("michibiki.video.video_rpc", new_callable=AsyncMock)
@patch("michibiki.db.update_video_job")
@patch("michibiki.db.get_video_job")
def test_progress_ws_marks_job_failed_when_polling_raises(mock_get_job, mock_update_job, mock_rpc):
    from fastapi import HTTPException

    mock_get_job.return_value = {"id": "job-1", "client_hash": "x", "status": "generating",
                                 "provider_operation_name": "operations/abc123"}
    mock_rpc.side_effect = HTTPException(403, "動画生成APIに接続できませんでした。")

    with patch("michibiki.video.client_hash", return_value="x"):
        with client.websocket_connect(
            "/api/video-jobs/job-1/progress", headers={"origin": "http://localhost:5173"},
        ) as websocket:
            websocket.send_json(HELLO)
            first = websocket.receive_json()
            assert first["status"] == "generating"
            second = websocket.receive_json()
            assert second["status"] == "failed"
    mock_update_job.assert_called_once_with("job-1", "failed")


@patch("michibiki.video._sign_video_url", return_value="https://signed.example/video.mp4")
@patch("michibiki.db.find_latest_video_job")
def test_get_video_by_report_returns_fresh_signed_url_when_ready(mock_find, mock_sign):
    mock_find.return_value = {"id": "job-1", "status": "ready", "object_name": "videos/job-1"}
    response = client.get("/api/videos/by-report/report-1", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "video_url": "https://signed.example/video.mp4", "job_id": "job-1"}
    mock_sign.assert_called_once_with("videos/job-1")


@patch("michibiki.db.find_latest_video_job")
def test_get_video_by_report_returns_status_without_url_when_not_ready(mock_find):
    mock_find.return_value = {"id": "job-1", "status": "generating", "object_name": None}
    response = client.get("/api/videos/by-report/report-1", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"status": "generating", "video_url": None, "job_id": "job-1"}


@patch("michibiki.db.find_latest_video_job", return_value=None)
def test_get_video_by_report_404s_when_no_job_exists(mock_find):
    response = client.get("/api/videos/by-report/report-1", headers=HEADERS)
    assert response.status_code == 404
