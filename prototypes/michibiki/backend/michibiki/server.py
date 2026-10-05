import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from copy import deepcopy

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import db
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
        async with asyncio.timeout(220):
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
    try:
        async with asyncio.timeout(240):
            result = await rpc("orchestrator", request.model_dump())
            result["timings"]["request_ms"] = round((time.monotonic() - started) * 1000)
            transient_places = result["places"]
            result["places"] = [{"place_id": p["place_id"]} for p in transient_places]
            saved = await asyncio.to_thread(db.finish_mission, mission["id"], result)
            response = deepcopy(saved)
            response["places"] = transient_places
            response["timings"]["request_ms"] = round(
                (time.monotonic() - started) * 1000
            )
            response["saved"] = False
            logger.info(
                "mission_completed id=%s elapsed_ms=%s",
                mission["id"],
                result["timings"]["request_ms"],
            )
            return response
    except TimeoutError:
        await asyncio.to_thread(db.fail_mission, mission["id"], "timeout")
        raise HTTPException(
            504, {"mission_id": mission["id"], "message": "処理期限を超えました。"}
        )
    except Exception:
        logger.exception("mission_failed id=%s", mission["id"])
        await asyncio.to_thread(db.fail_mission, mission["id"], "execution_failed")
        raise HTTPException(
            502,
            {
                "mission_id": mission["id"],
                "message": "分析に失敗しました。条件やAPI設定を確認してください。",
            },
        )


async def hydrate(result):
    output = deepcopy(result)
    ids = [p["place_id"] for p in output["places"]]
    if ids:
        hydrated = await rpc("orchestrator", {"op": "details", "place_ids": ids})
        output["places"] = hydrated["places"]
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
