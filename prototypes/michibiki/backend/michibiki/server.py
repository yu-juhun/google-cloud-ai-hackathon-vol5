import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from copy import deepcopy

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import db, experience_images
from .agents import pipeline, rpc, specialist
from .contracts import MissionInput, Profile

ROLE = os.environ.get("SERVICE_ROLE", "backend")
logger = logging.getLogger("michibiki")


@asynccontextmanager
async def lifespan(app):
    if ROLE == "backend":
        await asyncio.to_thread(db.migrate)
    yield


app = FastAPI(title=f"michibiki-{ROLE}", lifespan=lifespan)
if ROLE == "backend":
    from .media import client_hash, router as media_router
    from .video import router as video_router
    app.include_router(media_router)
    app.include_router(video_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173").split(","),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "X-Michibiki-Client"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": ROLE}


@app.post("/execute")
async def execute(payload: dict):
    if ROLE == "backend":
        raise HTTPException(404)
    if ROLE == "orchestrator":
        if payload.get("op") == "details":
            return await rpc("search", payload)
        async with asyncio.timeout(800):
            return await pipeline(payload)
    return await specialist(ROLE, payload)


def require_backend():
    if ROLE != "backend":
        raise HTTPException(404)


@app.put("/api/profile")
async def put_profile(profile: Profile, x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    return await asyncio.to_thread(db.save_profile, owner_id, profile.model_dump())


@app.get("/api/profile")
async def get_profile_endpoint(x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    conditions = await asyncio.to_thread(db.get_profile, owner_id)
    return conditions if conditions is not None else Profile().model_dump()


# Holds strong references to in-flight background mission tasks so they are
# never garbage-collected mid-run (asyncio only keeps a weak reference to a
# bare create_task() result); each task removes itself once done.
_background_missions = set()


async def _schedule_mission(coro):
    """Fire-and-forget by default. Tests monkeypatch this to `await coro`
    instead, so a mission's background work finishes deterministically
    before the test's POST call returns, instead of racing the test's own
    assertions against an unscheduled asyncio task."""
    task = asyncio.create_task(coro)
    _background_missions.add(task)
    task.add_done_callback(_background_missions.discard)


async def _run_mission(mission_id, owner_id, request, started):
    """Runs the actual (slow: tens of seconds to minutes) mission analysis in
    the background, after create_mission has already responded. Moved out of
    the request/response cycle because a single request held open for that
    long is exactly the kind of long-idle connection some clients (observed:
    Safari) silently drop mid-flight -- the backend was finishing and saving
    the result regardless, but the client had no way to find out. Polling
    GET /api/missions/{id} (short-lived requests) replaces waiting on this
    one connection's response."""
    try:
        async with asyncio.timeout(840):
            result = await rpc("orchestrator", request.model_dump())
            own_avatars = await asyncio.to_thread(
                db.avatar_object_names_owned_by, owner_id, request.avatar_object_names
            )
            await experience_images.generate(
                result,
                mission_id,
                avatar_object_names=own_avatars,
                budget=min(300, max(1, 835 - (time.monotonic() - started))),
            )
            result["timings"]["request_ms"] = round((time.monotonic() - started) * 1000)
            transient_places = result["places"]
            result["places"] = [{"place_id": p["place_id"]} for p in transient_places]
            await asyncio.to_thread(db.finish_mission, mission_id, result)
            logger.info(
                "mission_completed id=%s elapsed_ms=%s",
                mission_id,
                result["timings"]["request_ms"],
            )
    except TimeoutError:
        await asyncio.to_thread(db.fail_mission, mission_id, "timeout")
    except Exception:
        logger.exception("mission_failed id=%s", mission_id)
        await asyncio.to_thread(db.fail_mission, mission_id, "execution_failed")


@app.post("/api/missions")
async def create_mission(request: MissionInput, x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    started = time.monotonic()
    try:
        mission, created = await asyncio.to_thread(db.begin_mission, owner_id, request)
    except ValueError:
        raise HTTPException(409, "同じ依頼キーが別の入力に使われています。")
    if not created:
        if mission.get("result"):
            return await hydrate(mission["result"])
        raise HTTPException(
            409,
            {
                "mission_id": mission["id"],
                "status": mission["status"],
                "message": "この依頼は実行中または終了済みです。二重実行はしません。",
            },
        )
    await _schedule_mission(_run_mission(mission["id"], owner_id, request, started))
    return {"mission_id": mission["id"], "status": mission["status"]}


async def hydrate(result):
    output = deepcopy(result)
    ids = [p["place_id"] for p in output["places"]]
    if ids:
        hydrated = await rpc("orchestrator", {"op": "details", "place_ids": ids})
        output["places"] = hydrated["places"]
    await asyncio.to_thread(experience_images.attach_urls, output)
    return output


@app.get("/api/missions")
async def list_missions_endpoint(x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    return {"missions": await asyncio.to_thread(db.list_missions, owner_id)}


@app.get("/api/missions/{mission_id}")
async def get_mission(mission_id: str, x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    mission = await asyncio.to_thread(db.get_mission, owner_id, mission_id)
    if not mission:
        raise HTTPException(404, "依頼が見つかりません。")
    if not mission.get("result"):
        return {
            "mission_id": mission_id,
            "status": mission["status"],
            "error_code": mission.get("error_code"),
        }
    result = await hydrate(mission["result"])
    result["input"] = mission["input_snapshot"]
    result["saved"] = await asyncio.to_thread(db.is_itinerary_saved, mission_id)
    return result


@app.post("/api/missions/{mission_id}/save")
async def save(mission_id: str, x_michibiki_client: str = Header()):
    require_backend()
    owner_id = client_hash(x_michibiki_client)
    found = await asyncio.to_thread(db.save_itinerary, owner_id, mission_id)
    if not found:
        raise HTTPException(404)
    return {"mission_id": mission_id, "saved": True}
