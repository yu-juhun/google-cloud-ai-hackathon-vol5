import base64
import logging

from fastapi import FastAPI
from pydantic import BaseModel, Field

from prompts import build_prompt
from veo_client import start_video_task, video_task_status

app = FastAPI(title="video-agent")
logger = logging.getLogger(__name__)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class VideoJobRequest(BaseModel):
    image_bytes_b64: str = Field(max_length=9_000_000)
    image_mime_type: str
    report_text: str = Field(max_length=10_000)
    mobility_notes: str = Field(default="", max_length=2_000)
    feedback: str = Field(max_length=500)
    style: str
    tone: str


@app.post("/video-jobs")
async def create_video_job(request: VideoJobRequest) -> dict[str, str]:
    image_bytes = base64.b64decode(request.image_bytes_b64, validate=True)
    prompt = build_prompt(request.report_text, request.mobility_notes, request.style, request.tone, request.feedback)
    operation_name = start_video_task(image_bytes, request.image_mime_type, prompt)
    return {"operation_name": operation_name}


@app.get("/video-jobs/{operation_name:path}/status")
async def get_video_job_status(operation_name: str) -> dict:
    status, video_bytes, mime_type = video_task_status(operation_name)
    return {
        "status": status,
        "video_bytes_b64": base64.b64encode(video_bytes).decode("ascii") if video_bytes else None,
        "mime_type": mime_type,
    }
