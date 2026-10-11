"""Demo media access is scoped by a random browser capability, not a public owner ID."""
import asyncio
import hashlib
import json
import os
import random
from datetime import timedelta

import google.auth
import httpx
from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect
from google.auth.transport.requests import Request
from google.cloud import storage
from google.oauth2.id_token import fetch_id_token
from pydantic import BaseModel, Field

from . import db

router = APIRouter(prefix="/api")


def client_hash(token):
    if not token or not 32 <= len(token) <= 100:
        raise HTTPException(400, "このブラウザの画像アクセスキーがありません。")
    return hashlib.sha256(token.encode()).hexdigest()


async def persona_rpc(path, body=None):
    url = os.environ.get("PERSONA_URL", "").rstrip("/")
    if not url:
        raise HTTPException(503, "アバター・音声相談APIはまだ設定されていません。")
    token = await asyncio.to_thread(fetch_id_token, Request(), url)
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.request("POST" if body is not None else "GET", url + path,
                                        json=body, headers={"Authorization": f"Bearer {token}"})
    if response.is_error:
        detail = response.json().get("detail", "画像処理APIに接続できませんでした。")
        raise HTTPException(response.status_code, detail if isinstance(detail, str) else "画像の入力を確認してください。")
    return response.json()


class AvatarPhoto(BaseModel):
    photo: str = Field(max_length=9_000_000)
    consent: bool


@router.get("/avatar-templates")
async def templates():
    return await persona_rpc("/avatar-templates")


@router.get("/persona/capabilities")
async def capabilities():
    return await persona_rpc("/capabilities")


@router.post("/avatars")
async def create(photo: AvatarPhoto, x_michibiki_client: str = Header()):
    owner = client_hash(x_michibiki_client)
    catalog = await persona_rpc("/avatar-templates")
    all_ids = {t["id"] for categories in catalog.values() for templates in categories.values() for t in templates}
    version = await asyncio.to_thread(db.get_current_avatar_version, owner)
    used = await asyncio.to_thread(db.get_used_template_ids, owner, version)
    unused = list(all_ids - used)
    if len(unused) < 10:
        old_pool = await asyncio.to_thread(db.get_avatar_pool, owner, version)
        if old_pool:
            bucket = storage.Client().bucket(os.environ["AVATAR_BUCKET"])
            for entry in old_pool:
                bucket.blob(entry["object_name"]).delete()
            await asyncio.to_thread(db.delete_avatar_pool_version, owner, version)
        version += 1
        unused = list(all_ids)
    chosen = random.sample(unused, min(10, len(unused)))
    result = await persona_rpc("/avatar-jobs-batch", {
        "photo": photo.photo, "consent": photo.consent, "template_ids": chosen,
    })
    record = await asyncio.to_thread(db.create_avatar_set, owner, result["tasks"], version)
    return {"id": record["id"], "status": record["status"], "avatar_count": len(chosen)}


def signed_pool_assets(pool):
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    bucket = storage.Client(credentials=credentials).bucket(os.environ["AVATAR_BUCKET"])
    def sign(name):
        return bucket.blob(name).generate_signed_url(
            version="v4", expiration=timedelta(hours=1), method="GET",
            service_account_email=os.environ["AVATAR_SIGNER"], access_token=credentials.token,
        )
    return {"status": "ready",
            "avatars": [{"object_name": a["object_name"], "template_id": a["template_id"], "url": sign(a["object_name"])}
                       for a in pool],
            "expires_in": 3600}


@router.get("/avatars/pool")
async def pool(x_michibiki_client: str = Header()):
    owner = client_hash(x_michibiki_client)
    pool_rows = await asyncio.to_thread(db.get_avatar_pool, owner)
    selected = await asyncio.to_thread(db.get_profile_avatar, owner)
    signed = await asyncio.to_thread(signed_pool_assets, pool_rows)
    signed["selected"] = selected
    return signed


@router.get("/avatars/{set_id}")
async def get(set_id: str, x_michibiki_client: str = Header()):
    owner = client_hash(x_michibiki_client)
    record = await asyncio.to_thread(db.get_avatar_set, set_id, owner)
    if not record:
        raise HTTPException(404, "このブラウザの画像セットが見つかりません。")
    if record["status"] == "generating":
        result = await persona_rpc("/avatar-results-batch", {
            "tasks": record["provider_task_ids"], "set_id": set_id,
        })
        if result["status"] == "ready":
            await asyncio.to_thread(db.add_avatar_pool_entries, owner, record["version"], [
                {"template_id": a["template_id"], "object_name": a["object_name"]} for a in result["avatars"]
            ])
            current_avatar = await asyncio.to_thread(db.get_profile_avatar, owner)
            if not current_avatar:
                await asyncio.to_thread(db.set_profile_avatar, owner, result["avatars"][0]["object_name"])
            await asyncio.to_thread(db.update_avatar_set, set_id, "ready")
            record["status"] = "ready"
        elif result["status"] == "failed":
            await asyncio.to_thread(db.update_avatar_set, set_id, "failed")
            record["status"] = "failed"
    if record["status"] == "ready":
        pool = await asyncio.to_thread(db.get_avatar_pool, owner, record["version"])
        return await asyncio.to_thread(signed_pool_assets, pool)
    return {"id": set_id, "status": record["status"]}


class AvatarSelection(BaseModel):
    object_name: str


@router.put("/profile/avatar")
async def select_avatar(selection: AvatarSelection, x_michibiki_client: str = Header()):
    owner = client_hash(x_michibiki_client)
    pool_rows = await asyncio.to_thread(db.get_avatar_pool, owner)
    if not any(row["object_name"] == selection.object_name for row in pool_rows):
        raise HTTPException(404, "指定されたアバターが見つかりません。")
    await asyncio.to_thread(db.set_profile_avatar, owner, selection.object_name)
    return {"status": "ok"}


@router.websocket("/persona/converse")
async def converse(websocket: WebSocket):
    """Keep persona Cloud Run private; relay audio without logging or storing it."""
    allowed = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
    if websocket.headers.get("origin") not in allowed:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    tasks = []
    try:
        async with asyncio.timeout(300):
            hello = await asyncio.wait_for(websocket.receive_text(), timeout=10)
            if len(hello) > 512:
                raise ValueError("Invalid session handshake")
            owner = client_hash(json.loads(hello).get("client_token"))
            url = os.environ["PERSONA_URL"].rstrip("/")
            token = await asyncio.to_thread(fetch_id_token, Request(), url)
            voice = websocket.query_params.get("voice", "Kore")
            if voice not in ("Puck", "Charon", "Kore", "Leda"):
                raise ValueError("Invalid voice")
            purpose = websocket.query_params.get("purpose", "trip_wish")
            if purpose not in ("trip_wish", "video_feedback"):
                raise ValueError("Invalid purpose")
            import websockets
            async with websockets.connect(
                url.replace("https://", "wss://") + f"/ws/converse?mode=intake&voice={voice}&purpose={purpose}",
                extra_headers={"Authorization": f"Bearer {token}"}, max_size=5_000_000,
            ) as upstream:
                await websocket.send_json({"type": "session_ready"})
                async def send():
                    while True:
                        message = await websocket.receive_text()
                        if len(message) > 100_000:
                            raise ValueError("Audio message too large")
                        data = json.loads(message)
                        if data.get("type") not in ("audio_chunk", "finish", "context"):
                            continue
                        await upstream.send(message)
                async def receive():
                    async for message in upstream:
                        data = json.loads(message)
                        if data.get("type") == "persona_result":
                            body = {key: value for key, value in data["data"].items() if not key.startswith("avatar_")}
                            body["consultation_id"] = await asyncio.to_thread(db.save_consultation, owner, body)
                            data["data"] = body
                            await websocket.send_json(data)
                            return
                        if data.get("type") in ("start_error", "finish_error"):
                            data["message"] = "音声相談の処理に失敗しました。文字入力でも続けられます。"
                        await websocket.send_json(data)
                tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.send_json({"type": "start_error", "message": "音声相談に接続できませんでした。文字入力で続けられます。"})
        except Exception:
            pass
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await websocket.close()
        except Exception:
            pass
