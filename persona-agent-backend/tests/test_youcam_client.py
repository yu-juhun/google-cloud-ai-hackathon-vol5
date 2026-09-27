# persona-agent-backend/tests/test_youcam_client.py
import base64
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import youcam_client
from youcam_client import _get_access_token, generate_base_avatar


def _file_and_task_responses():
    file_create_resp = MagicMock()
    file_create_resp.json.return_value = {
        "data": {
            "files": [
                {
                    "file_id": "file-123",
                    "requests": [{"method": "PUT", "url": "https://upload.example/x", "headers": {}}],
                }
            ]
        }
    }
    task_create_resp = MagicMock()
    task_create_resp.json.return_value = {"data": {"task_id": "task-abc"}}
    return file_create_resp, task_create_resp


@patch("youcam_client._get_access_token", return_value="fake-token")
@patch("youcam_client.requests.get")
@patch("youcam_client.requests.request")
@patch("youcam_client.requests.post")
def test_generate_base_avatar_full_flow(mock_post, mock_request, mock_get, _mock_token):
    file_create_resp = MagicMock()
    file_create_resp.json.return_value = {
        "data": {
            "files": [
                {
                    "file_id": "file-123",
                    "requests": [{"method": "PUT", "url": "https://upload.example/x", "headers": {"Content-Type": "image/png"}}],
                }
            ]
        }
    }
    task_create_resp = MagicMock()
    task_create_resp.json.return_value = {"data": {"task_id": "task-abc"}}
    mock_post.side_effect = [file_create_resp, task_create_resp]

    upload_resp = MagicMock()
    mock_request.return_value = upload_resp

    poll_resp = MagicMock()
    poll_resp.json.return_value = {
        "data": {
            "task_status": "success",
            "results": {"output": [{"url": "https://result.example/avatar.jpg"}]},
        }
    }
    download_resp = MagicMock()
    download_resp.content = b"fake-image-bytes"
    download_resp.headers = {"Content-Type": "image/jpeg"}
    mock_get.side_effect = [poll_resp, download_resp]

    result = generate_base_avatar(photo_bytes=b"fake-photo-bytes", content_type="image/png")

    assert result == (b"fake-image-bytes", "image/jpeg")
    mock_request.assert_called_once_with(
        "PUT", "https://upload.example/x", headers={"Content-Type": "image/png"}, data=b"fake-photo-bytes", timeout=30
    )


@patch("youcam_client._get_access_token", return_value="fake-token")
@patch("youcam_client.requests.get")
@patch("youcam_client.requests.request")
@patch("youcam_client.requests.post")
def test_generate_base_avatar_raises_on_task_error_status(mock_post, mock_request, mock_get, _mock_token):
    file_create_resp, task_create_resp = _file_and_task_responses()
    mock_post.side_effect = [file_create_resp, task_create_resp]
    mock_request.return_value = MagicMock()

    error_poll_resp = MagicMock()
    error_poll_resp.json.return_value = {"data": {"task_status": "error", "error_message": "no face detected"}}
    mock_get.return_value = error_poll_resp

    with pytest.raises(RuntimeError, match="task-abc"):
        generate_base_avatar(photo_bytes=b"fake-photo-bytes", content_type="image/png")


@patch("youcam_client.time.sleep")
@patch("youcam_client._get_access_token", return_value="fake-token")
@patch("youcam_client.requests.get")
@patch("youcam_client.requests.request")
@patch("youcam_client.requests.post")
def test_generate_base_avatar_raises_on_poll_timeout(mock_post, mock_request, mock_get, _mock_token, _mock_sleep):
    file_create_resp, task_create_resp = _file_and_task_responses()
    mock_post.side_effect = [file_create_resp, task_create_resp]
    mock_request.return_value = MagicMock()

    pending_poll_resp = MagicMock()
    pending_poll_resp.json.return_value = {"data": {"task_status": "processing"}}
    mock_get.return_value = pending_poll_resp

    with pytest.raises(RuntimeError, match="did not finish"):
        generate_base_avatar(photo_bytes=b"fake-photo-bytes", content_type="image/png")

    assert mock_get.call_count == youcam_client.MAX_POLL_ATTEMPTS


def test_get_access_token_encrypts_payload_and_parses_result_envelope(monkeypatch):
    """Exercises _get_access_token directly with a real throwaway RSA
    keypair, so the actual RSA-encryption/id_token-construction code path
    runs (not just a @patch-ed-out stub), and covers the /client/auth
    endpoint's anomalous ["result"] response envelope (every other YouCam
    endpoint uses ["data"])."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_b64 = base64.b64encode(public_key_der).decode()

    monkeypatch.setenv("PERFECTCORP_API_KEY", "fake-client-id")
    monkeypatch.setenv("PERFECTCORP_API_SECRET", public_key_b64)

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"status": 200, "result": {"access_token": "fake-token"}}

    with patch("youcam_client.requests.post", return_value=fake_resp) as mock_post:
        token = _get_access_token()

    assert token == "fake-token"
    body = mock_post.call_args.kwargs["json"]
    assert body["client_id"] == "fake-client-id"
    assert isinstance(body["id_token"], str)
    assert len(body["id_token"]) > 0


@patch("youcam_client._get_access_token", return_value="fake-token")
@patch("youcam_client.requests.get")
def test_list_avatar_templates_paginates_and_derives_gender(mock_get, _mock_token):
    youcam_client._template_catalog_cache = None
    page1 = MagicMock()
    page1.json.return_value = {
        "data": {
            "templates": [{"id": "female_manga_mood", "title": "Manga Mood", "category_name": "Anime"}],
            "next_token": "abc",
        }
    }
    page2 = MagicMock()
    page2.json.return_value = {
        "data": {
            "templates": [{"id": "male_yearbook", "title": "Yearbook", "category_name": "Lifestyle"}],
        }
    }
    mock_get.side_effect = [page1, page2]

    templates = youcam_client.list_avatar_templates()

    assert templates == [
        {"id": "female_manga_mood", "title": "Manga Mood", "category": "Anime", "gender": "female"},
        {"id": "male_yearbook", "title": "Yearbook", "category": "Lifestyle", "gender": "male"},
    ]
    assert mock_get.call_count == 2


@patch("youcam_client._get_access_token", return_value="fake-token")
@patch("youcam_client.requests.get")
def test_list_avatar_templates_caches_after_first_call(mock_get, _mock_token):
    youcam_client._template_catalog_cache = None
    page = MagicMock()
    page.json.return_value = {"data": {"templates": [{"id": "female_manga_mood", "title": "x", "category_name": "y"}]}}
    mock_get.return_value = page

    youcam_client.list_avatar_templates()
    youcam_client.list_avatar_templates()

    assert mock_get.call_count == 1
