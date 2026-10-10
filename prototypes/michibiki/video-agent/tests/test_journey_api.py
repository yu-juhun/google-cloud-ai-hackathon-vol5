from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from journey_api import ComposeRequest, media_object, render_movie
from veo_client import start_reference_task


def test_reject_objects_outside_private_journey_prefix():
    for name in ["avatars/person.png", "videos/journeys/not-uuid/scene.mp4", "videos/journeys/../x.mp4"]:
        with pytest.raises(ValueError):
            media_object(name)


def test_reference_to_video_uses_same_person_and_venue():
    client = MagicMock()
    client.models.generate_videos.return_value.name = "operations/scene-1"
    with patch("veo_client._build_client", return_value=client):
        assert start_reference_task([(b"person", "image/png"), (b"venue", "image/jpeg")], "scene data") == "operations/scene-1"
    call = client.models.generate_videos.call_args.kwargs
    assert [r.image.image_bytes for r in call["config"].reference_images] == [b"person", b"venue"]
    assert call["config"].duration_seconds == 8
    assert call["source"].image is None
    client.close.assert_called_once()


def test_reuse_completed_movie_without_composing_again():
    blob = MagicMock()
    blob.exists.return_value = True
    blob.metadata = {"render": '{"duration_seconds":24.3}'}
    job_id = uuid4()
    with patch("journey_api.media_object", return_value=blob), patch("journey_api.compose") as compose:
        result = render_movie(ComposeRequest(job_id=job_id, scenes=[{"name": "place"}]))
    assert result["object_name"] == f"videos/journeys/{job_id}/journey.mp4"
    assert result["render"]["duration_seconds"] == 24.3
    compose.assert_not_called()
