"""Saved itinerary -> bounded Veo scenes -> durable, smoothly edited movie.

Progress is driven by authenticated reads, not a detached Cloud Run task. An
unknown submission outcome is never automatically charged a second time.
"""
import asyncio
import base64
from copy import deepcopy
import html
import json
import logging
import os
from pathlib import Path
import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import db
from .media import client_hash
from .video import (_download_avatar_image, _download_experience_image,
                    _sign_video_url, _upload_video, check_relevance, video_rpc)

router = APIRouter(prefix="/api/journey-videos")
logger = logging.getLogger("michibiki.journey_video")
REFERENCES = json.loads(Path(__file__).with_name("journey_references.json").read_text())


class JourneyRequest(BaseModel):
    mission_id: str
    feedback: str = Field(default="", max_length=500)
    consent: bool


def image_payload(raw):
    if not raw or len(raw) > 6_000_000:
        raise ValueError("Invalid reference size")
    mime = "image/jpeg" if raw.startswith(b"\xff\xd8") else "image/png" if raw.startswith(b"\x89PNG") else None
    if not mime:
        raise ValueError("References must be PNG or JPEG")
    return {"bytes_b64": base64.b64encode(raw).decode(), "mime_type": mime}


def storyboard(mission, names):
    result = mission["result"]
    stops = result["itinerary"]["stops"]
    # Spread a longer itinerary across its full chronology, including the end.
    indexes = list(range(len(stops))) if len(stops) <= 4 else [round(i * (len(stops) - 1) / 3) for i in range(4)]
    if not indexes:
        raise HTTPException(400, "旅程に訪問先がありません。")
    scenes = []
    for i in indexes:
        stop = stops[i]
        assessment = next((a for t in result["twins"] for a in t.get("assessments", [])
                           if a.get("place_id") == stop["place_id"]), {})
        if assessment.get("status") == "not_accessible":
            continue
        image = next((t.get("experience_image", {}) for t in result["twins"]
                      if t.get("experience_image", {}).get("place_id") == stop["place_id"]), {})
        scenes.append({"place_id": stop["place_id"], "name": names.get(stop["place_id"], "旅先"),
                       "activity": stop["activity"], "facts": assessment.get("facts", [])[:4],
                       "status": "waiting", "experience_image": image})
    if not scenes:
        raise HTTPException(400, "動画に使える旅程の候補がありません。")
    return scenes


async def venue_reference(place_id):
    """Only reviewed place-ID mappings; no arbitrary web photo or Maps reuse."""
    location = next((r for r in REFERENCES if r["place_id"] == place_id), None)
    if not location:
        return None
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "MichibikiJourney/1.0"}) as client:
        response = await client.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "format": "json", "titles": location["commons_file"],
            "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1280})
        response.raise_for_status()
        info = next(iter(response.json()["query"]["pages"].values()))["imageinfo"][0]
        meta = info["extmetadata"]
        license_name = meta.get("LicenseShortName", {}).get("value", "")
        if license_name not in ("CC0", "Public domain", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0"):
            return None
        for url in dict.fromkeys([info.get("thumburl", info["url"]), info["url"]]):
            if urlparse(url).scheme != "https" or urlparse(url).hostname != "upload.wikimedia.org":
                continue
            response = await client.get(url)
            if response.is_success:
                image_payload(response.content)
                author = html.unescape(re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", "")))
                return response.content, {"author": author[:150], "license": license_name,
                    "source": info["descriptionurl"], "license_url": meta.get("LicenseUrl", {}).get("value", "")}
    return None


@router.post("")
async def create_journey(request: JourneyRequest, x_michibiki_client: str = Header()):
    if not request.consent:
        raise HTTPException(400, "動画生成への同意が必要です。")
    owner = client_hash(x_michibiki_client)
    mission = await asyncio.to_thread(db.get_mission, owner, request.mission_id)
    if not mission or not mission.get("result"):
        raise HTTPException(404, "保存済みの旅程が見つかりません。")
    existing = await asyncio.to_thread(db.find_journey_video, owner, request.mission_id)
    if existing and existing["status"] == "failed" and existing["body"].get("prepared") and all(
        scene.get("status") == "ready" and scene.get("object_name") for scene in existing["body"]["scenes"]
    ):
        # Editing failed AFTER generation: reuse every saved scene, not a new billable job.
        body = deepcopy(existing["body"])
        body.pop("error", None)
        await asyncio.to_thread(db.save_journey_video, existing["id"], "rendering", body)
        return {"id": existing["id"], "status": "rendering"}
    if existing and existing["status"] != "failed":
        return {"id": existing["id"], "status": existing["status"]}
    # Rehydrate names from Places without persisting the provider's raw payload.
    from .server import hydrate
    hydrated = await hydrate(mission["result"])
    names = {p["place_id"]: p["name"] for p in hydrated["places"]}
    plan = storyboard(mission, names)
    on_topic, reason = await asyncio.to_thread(check_relevance,
        json.dumps(mission["result"]["itinerary"], ensure_ascii=False), request.feedback, None)
    if not on_topic:
        raise HTTPException(400, reason or "旅程に関連する希望を入力してください。")
    body = {"version": 1, "prepared": False, "scenes": plan, "feedback": request.feedback,
            "trip": mission["input_snapshot"]["trip"],
            "chair": mission["input_snapshot"]["profile"]["chair"]}
    job, created = await asyncio.to_thread(db.begin_journey_video, owner, request.mission_id, body)
    if not created:
        return {"id": job["id"], "status": job["status"]}
    prefix = f"videos/journeys/{job['id']}/"
    try:
        avatar = await asyncio.to_thread(db.find_latest_ready_avatar_set, owner)
        if avatar:
            person = await asyncio.to_thread(_download_avatar_image, avatar)
            body["person_kind"] = "saved_avatar"
        else:
            url = os.environ.get("EXPERIENCE_REFERENCE_URL", "")
            # This is a server-controlled demo asset URL, never user-supplied.
            allowed_hosts = {urlparse(origin).hostname for origin in os.environ.get("FRONTEND_ORIGIN", "").split(",")}
            allowed_hosts.add("storage.googleapis.com")
            if urlparse(url).scheme != "https" or urlparse(url).hostname not in allowed_hosts:
                raise HTTPException(503, "人物の参照画像が未設定です。")
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)
                response.raise_for_status()
                person = response.content
            body["person_kind"] = "demo_reference"
        payload = image_payload(person)
        body["person_object"] = prefix + "person-reference"
        body["person_mime"] = payload["mime_type"]
        await asyncio.to_thread(_upload_video, body["person_object"], person, body["person_mime"])
        for index, scene in enumerate(body["scenes"]):
            reference = None
            try:
                reference = await venue_reference(scene["place_id"])
            except (httpx.HTTPError, ValueError, KeyError, StopIteration):
                logger.warning("journey_reference_unavailable job_id=%s scene=%s", job["id"], index)
            raw, credit = reference if reference else (None, None)
            scene["reference_kind"] = "licensed_venue" if raw else "text_imagined"
            illustration = scene.pop("experience_image", {})
            if raw is None and illustration.get("status") == "ready":
                raw = await asyncio.to_thread(_download_experience_image, illustration)
                scene["reference_kind"] = "generated_experience"
            if raw:
                scene["reference_object"] = prefix + f"scene-{index + 1}-reference"
                scene["reference_mime"] = image_payload(raw)["mime_type"]
                await asyncio.to_thread(_upload_video, scene["reference_object"], raw, scene["reference_mime"])
            if credit:
                scene["credit"] = credit
        body["prepared"] = True
        await asyncio.to_thread(db.save_journey_video, job["id"], "queued", body)
    except Exception:
        body["error"] = "reference_preparation_failed"
        await asyncio.to_thread(db.save_journey_video, job["id"], "failed", body)
        raise
    return {"id": job["id"], "status": "queued", "scene_count": len(plan)}


async def advance(job):
    body = deepcopy(job["body"])
    if not body.get("prepared") or job["status"] in ("ready", "failed"):
        return
    if not await asyncio.to_thread(db.claim_journey_progress, job["id"]):
        return
    prefix = f"videos/journeys/{job['id']}/"
    try:
        # Another poll may have advanced the job between our read and lease.
        fresh = await asyncio.to_thread(db.get_journey_video, job["id"], job["client_hash"])
        if not fresh or fresh["status"] in ("ready", "failed"):
            return
        body = deepcopy(fresh["body"])
        scene = next((s for s in body["scenes"] if s["status"] != "ready"), None)
        if scene:
            index = body["scenes"].index(scene)
            if scene["status"] == "submitting":
                # A prior invocation stopped before recording the operation.
                # Do not guess that it was never charged and resubmit it.
                body["error"] = "submission_outcome_unknown"
                await asyncio.to_thread(db.save_journey_video, job["id"], "failed", body)
                return
            if not scene.get("operation"):
                scene["status"] = "submitting"
                await asyncio.to_thread(db.save_journey_video, job["id"], "generating", body)
                result = await video_rpc("/journey-scenes", {
                    "person_object": body["person_object"], "person_mime": body["person_mime"],
                    "reference_object": scene.get("reference_object"),
                    "reference_mime": scene.get("reference_mime"),
                    "reference_kind": scene["reference_kind"], "scene": scene,
                    "trip": body["trip"], "chair": body["chair"],
                    "feedback": body["feedback"], "index": index, "count": len(body["scenes"]),
                })
                scene.update(operation=result["operation_name"], status="generating")
                await asyncio.to_thread(db.save_journey_video, job["id"], "generating", body)
                return
            result = await video_rpc(f"/video-jobs/{scene['operation']}/status")
            if result["status"] == "failed":
                body["error"] = "scene_generation_failed"
                await asyncio.to_thread(db.save_journey_video, job["id"], "failed", body)
                return
            if result["status"] == "ready":
                raw = base64.b64decode(result["video_bytes_b64"], validate=True)
                if not raw:
                    raise ValueError("Empty clip")
                scene.update(status="ready", object_name=prefix + f"scene-{index + 1}.mp4")
                await asyncio.to_thread(_upload_video, scene["object_name"], raw, "video/mp4")
                await asyncio.to_thread(db.save_journey_video, job["id"], "generating", body)
            return
        await asyncio.to_thread(db.save_journey_video, job["id"], "rendering", body)
        result = await video_rpc("/journey-compose", {"job_id": job["id"], "scenes": body["scenes"]})
        body["render"] = result["render"]
        await asyncio.to_thread(db.save_journey_video, job["id"], "ready", body, result["object_name"])
    except (HTTPException, httpx.HTTPError) as exc:
        logger.warning("journey_progress_retry job_id=%s error_type=%s", job["id"], type(exc).__name__)
        # A submit of unknown outcome is left as 'submitting', not retried.
        if isinstance(exc, HTTPException) and exc.status_code not in (429, 500, 502, 503, 504):
            body["error"] = "provider_error"
            await asyncio.to_thread(db.save_journey_video, job["id"], "failed", body)
    except (ValueError, KeyError):
        body["error"] = "invalid_video_result"
        await asyncio.to_thread(db.save_journey_video, job["id"], "failed", body)
    finally:
        await asyncio.to_thread(db.release_journey_progress, job["id"])


@router.get("/by-mission/{mission_id}")
async def get_journey(mission_id: str, x_michibiki_client: str = Header()):
    owner = client_hash(x_michibiki_client)
    job = await asyncio.to_thread(db.find_journey_video, owner, mission_id)
    if not job:
        raise HTTPException(404, "この旅の動画はまだありません。")
    await advance(job)
    job = await asyncio.to_thread(db.find_journey_video, owner, mission_id)
    scenes = job["body"]["scenes"]
    return {"job_id": job["id"], "status": job["status"],
            "scene_count": len(scenes), "completed_scenes": sum(s["status"] == "ready" for s in scenes),
            "scenes": [{"name": s["name"], "status": s["status"], "reference_kind": s.get("reference_kind")} for s in scenes],
            "video_url": await asyncio.to_thread(_sign_video_url, job["object_name"]) if job["status"] == "ready" else None,
            "error": job["body"].get("error"), "render": job["body"].get("render"),
            "credits": [s["credit"] for s in scenes if s.get("credit")]}
