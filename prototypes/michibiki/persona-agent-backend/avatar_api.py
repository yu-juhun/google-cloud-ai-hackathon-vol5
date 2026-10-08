"""Private Cloud Run API: YouCam batches and generated assets, never source photos."""
import asyncio
import base64
import io
import logging
import os
from uuid import UUID

from fastapi import APIRouter, HTTPException
from google import genai
from google.cloud import storage
from PIL import Image
from pydantic import BaseModel, Field

from avatar_generation import generate_open_mouth_variant
from youcam_client import (avatar_task_status, download_avatar, flatten_template_ids,
                           load_avatar_template_catalog, start_avatar_task)

router = APIRouter()
logger = logging.getLogger(__name__)
Image.MAX_IMAGE_PIXELS = 20_000_000


class AvatarPhoto(BaseModel):
    photo: str = Field(max_length=9_000_000)
    template_id: str = Field(max_length=100)
    consent: bool


class AvatarResult(BaseModel):
    task_id: str = Field(min_length=1, max_length=500)
    set_id: UUID


@router.get("/capabilities")
def capabilities():
    return {"avatar_configured": bool(os.environ.get("PERFECTCORP_API_KEY") and
                                       os.environ.get("PERFECTCORP_API_SECRET")),
            "avatar_count": 11, "voice_model": "gemini-live-2.5-flash-native-audio"}


def submit(photo):
    if not photo.consent:
        raise HTTPException(400, "写真をYouCamへ送信することへの確認が必要です。")
    if not capabilities()["avatar_configured"]:
        raise HTTPException(503, "YouCamのAPIキー・シークレットが未設定です。")
    if photo.template_id not in flatten_template_ids(load_avatar_template_catalog()):
        raise HTTPException(400, "スタイルを選び直してください。")
    try:
        raw = base64.b64decode(photo.photo, validate=True)
        if len(raw) > 6_000_000:
            raise ValueError("Photo too large")
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ("JPEG", "PNG") or max(image.size) > 4096:
                raise ValueError("Unsupported photo")
            mime = Image.MIME[image.format]
            image.verify()
    except Exception:
        raise HTTPException(400, "6MB以下・長辺4096px以下のJPEG/PNG写真を選んでください。")
    return {"task_id": start_avatar_task(raw, mime, photo.template_id, 11)}


@router.post("/avatar-jobs")
async def create_avatar_job(photo: AvatarPhoto):
    try:
        return await asyncio.to_thread(submit, photo)
    except HTTPException:
        raise
    except Exception:
        logger.warning("YouCam submission failed", exc_info=False)
        raise HTTPException(502, "YouCamへの画像生成依頼に失敗しました。")


def collect(request):
    status, outputs = avatar_task_status(request.task_id)
    if status == "error":
        return {"status": "failed"}
    if status != "success":
        return {"status": "generating"}
    if len(outputs) != 11:
        raise ValueError("YouCam did not return eleven avatars")
    bucket = storage.Client().bucket(os.environ["AVATAR_BUCKET"])
    assets = []
    for ordinal, output in enumerate(outputs):
        raw, mime = download_avatar(output["url"])
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        object_name = f"avatars/{request.set_id}/{ordinal:02d}"
        blob = bucket.blob(object_name)
        blob.cache_control = "private, max-age=3600"
        blob.upload_from_string(raw, content_type=mime)
        assets.append({"ordinal": ordinal, "object_name": object_name, "mime_type": mime})
        if ordinal == 0:
            base, base_mime = raw, mime
    # One auxiliary mouth-open frame for voice discussion; not an extra twin.
    mouth_open = None
    client = genai.Client(vertexai=True, project=os.environ["VERTEX_PROJECT_ID"],
                          location=os.environ.get("IMAGE_LOCATION", "global"))
    try:
        opened = generate_open_mouth_variant(base, client, mime_type=base_mime)
        if opened != base:
            object_name = f"avatars/{request.set_id}/mouth-open"
            with Image.open(io.BytesIO(opened)) as image:
                mime = Image.MIME[image.format]
            bucket.blob(object_name).upload_from_string(opened, content_type=mime)
            mouth_open = object_name
    except Exception:
        logger.warning("Mouth-open image unavailable; avatars remain usable")
    finally:
        client.close()
    return {"status": "ready", "assets": assets, "mouth_open": mouth_open}


@router.post("/avatar-results")
async def avatar_result(request: AvatarResult):
    try:
        return await asyncio.to_thread(collect, request)
    except Exception as exc:
        logger.warning("Avatar batch collection failed error_type=%s", type(exc).__name__, exc_info=False)
        raise HTTPException(502, "生成画像を取得・保存できませんでした。再確認してください。")
