from unittest.mock import MagicMock, patch

import veo_client
from google.genai import types


@patch("veo_client._build_client")
def test_start_video_task_returns_operation_name(mock_build_client):
    fake_operation = MagicMock(name="operations/abc123")
    fake_operation.name = "operations/abc123"
    fake_client = MagicMock()
    fake_client.models.generate_videos.return_value = fake_operation
    mock_build_client.return_value = fake_client

    operation_name = veo_client.start_video_task(b"fake-image-bytes", "image/png", "a calm cafe scene")

    assert operation_name == "operations/abc123"
    call_kwargs = fake_client.models.generate_videos.call_args.kwargs
    assert call_kwargs["model"] == veo_client.VEO_MODEL
    source = call_kwargs["source"]
    assert source.prompt == "a calm cafe scene"
    assert source.image.image_bytes == b"fake-image-bytes"
    assert source.image.mime_type == "image/png"


@patch("veo_client._build_client")
def test_video_task_status_still_generating(mock_build_client):
    fake_operation = MagicMock(done=None)
    fake_client = MagicMock()
    fake_client.operations.get.return_value = fake_operation
    mock_build_client.return_value = fake_client

    status, video_bytes, mime_type = veo_client.video_task_status("operations/abc123")

    assert status == "generating"
    assert video_bytes is None
    assert mime_type is None
    call_args = fake_client.operations.get.call_args.args
    assert isinstance(call_args[0], types.GenerateVideosOperation)
    assert call_args[0].name == "operations/abc123"


@patch("veo_client._build_client")
def test_video_task_status_ready(mock_build_client):
    fake_video = MagicMock(video_bytes=b"fake-video-bytes", mime_type="video/mp4")
    fake_generated = MagicMock(video=fake_video)
    fake_result = MagicMock(generated_videos=[fake_generated])
    fake_operation = MagicMock(done=True, error=None, result=fake_result)
    fake_client = MagicMock()
    fake_client.operations.get.return_value = fake_operation
    mock_build_client.return_value = fake_client

    status, video_bytes, mime_type = veo_client.video_task_status("operations/abc123")

    assert status == "ready"
    assert video_bytes == b"fake-video-bytes"
    assert mime_type == "video/mp4"


@patch("veo_client._build_client")
def test_video_task_status_failed(mock_build_client):
    fake_operation = MagicMock(
        done=True,
        error={"code": 3, "message": "Unsupported image format. Expected JPEG or PNG."},
        result=None,
    )
    fake_client = MagicMock()
    fake_client.operations.get.return_value = fake_operation
    mock_build_client.return_value = fake_client

    status, video_bytes, mime_type = veo_client.video_task_status("operations/abc123")

    assert status == "failed"
    assert video_bytes is None
    assert mime_type is None


@patch("veo_client._build_client")
def test_video_task_status_rai_filtered_returns_failed(mock_build_client):
    # Veo's responsible-AI filtering can finish the operation (done=True,
    # error=None) but return zero generated videos.
    fake_result = MagicMock(generated_videos=[])
    fake_operation = MagicMock(done=True, error=None, result=fake_result)
    fake_client = MagicMock()
    fake_client.operations.get.return_value = fake_operation
    mock_build_client.return_value = fake_client

    status, video_bytes, mime_type = veo_client.video_task_status("operations/abc123")

    assert status == "failed"
    assert video_bytes is None
    assert mime_type is None
