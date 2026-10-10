"""Thin wrapper around google-genai's Veo video generation.

Model name and call shape below were verified against the real Vertex AI
API (dispatch message for Task 4, 2026-10-05):

- VEO_MODEL confirmed as "veo-3.1-generate-001" via client.models.list().
- The `generate_videos(model=..., prompt=..., image=...)` call shape is
  deprecated in the installed google-genai SDK (DeprecationWarning
  observed; removal not before 2026-07-31). Use the `source=` /
  `GenerateVideosSource` shape instead.
- `operation.done` is `None` while still running, not `False`.
- `operation.error` is a plain dict with `code`/`message` keys on failure,
  and `operation.result` is `None` in that case.
- Without `output_gcs_uri` set, Veo returns the video inline as
  `video.video_bytes` (not `video.uri`, which is `None`).

Do not change the model name or call shape without re-verifying against
the real API.
"""
import os

from google import genai
from google.genai import types

VEO_MODEL = "veo-3.1-generate-001"


def _build_client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=os.environ["VERTEX_PROJECT_ID"],
        location=os.environ.get("VERTEX_LOCATION", "us-central1"),
    )


def start_video_task(image_bytes: bytes, image_mime_type: str, prompt: str) -> str:
    """Starts a Veo generation and returns the long-running operation's name
    immediately — this call does not wait for completion."""
    client = _build_client()
    operation = client.models.generate_videos(
        model=VEO_MODEL,
        source=types.GenerateVideosSource(
            prompt=prompt,
            image=types.Image(image_bytes=image_bytes, mime_type=image_mime_type),
        ),
        # Veo only supports "16:9" or "9:16" (per the installed SDK's own
        # field description) — 16:9 matches how the generated video is
        # displayed (a wide <video> element in the results page).
        config=types.GenerateVideosConfig(number_of_videos=1, aspect_ratio="16:9"),
    )
    return operation.name


def video_task_status(operation_name: str) -> tuple[str, bytes | None, str | None]:
    """Polls the operation once (no internal sleep/retry — callers decide
    polling cadence). Returns (status, video_bytes, mime_type); the latter
    two are only non-None when status == "ready"."""
    client = _build_client()
    operation = client.operations.get(types.GenerateVideosOperation(name=operation_name))
    if not operation.done:
        return "generating", None, None
    if operation.error:
        return "failed", None, None
    if not operation.result or not operation.result.generated_videos:
        # Veo's responsible-AI filtering can report done=True with no error
        # and no generated videos; treat that the same as a failure.
        return "failed", None, None
    video = operation.result.generated_videos[0].video
    return "ready", video.video_bytes, video.mime_type
