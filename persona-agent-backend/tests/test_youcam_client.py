# persona-agent-backend/tests/test_youcam_client.py
from unittest.mock import MagicMock, patch

from youcam_client import generate_base_avatar


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
    mock_get.side_effect = [poll_resp, download_resp]

    result = generate_base_avatar(photo_bytes=b"fake-photo-bytes", content_type="image/png")

    assert result == b"fake-image-bytes"
    mock_request.assert_called_once_with(
        "PUT", "https://upload.example/x", headers={"Content-Type": "image/png"}, data=b"fake-photo-bytes", timeout=30
    )
