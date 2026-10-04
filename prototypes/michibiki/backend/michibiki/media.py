"""Demo media access is scoped by a random browser capability, not a public owner ID."""
import asyncio
import hashlib
import json
import os
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
    template_id: str = Field(max_length=100)
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
    result = await persona_rpc("/avatar-jobs", photo.model_dump())
    record = await asyncio.to_thread(db.create_avatar_set, owner, result["task_id"])
    return {"id": record["id"], "status": record["status"], "avatar_count": 11}


def signed_assets(record):
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    bucket = storage.Client(credentials=credentials).bucket(os.environ["AVATAR_BUCKET"])
    def sign(name):
        return bucket.blob(name).generate_signed_url(
            version="v4", expiration=timedelta(hours=1), method="GET",
            service_account_email=os.environ["AVATAR_SIGNER"], access_token=credentials.token,
        )
    assets = record["assets"]
    return {"id": record["id"], "status": "ready",
            "images": [sign(a["object_name"]) for a in assets["assets"]],
            "mouth_open": sign(assets["mouth_open"]) if assets.get("mouth_open") else None,
            "expires_in": 3600}


@router.get("/avatars/{set_id}")
async def get(set_id: str, x_michibiki_client: str = Header()):
    record = await asyncio.to_thread(db.get_avatar_set, set_id, client_hash(x_michibiki_client))
    if not record:
        raise HTTPException(404, "このブラウザの画像セットが見つかりません。")
    if record["status"] == "generating":
        result = await persona_rpc("/avatar-results", {"task_id": record["provider_task_id"], "set_id": set_id})
        if result["status"] in ("ready", "failed"):
            await asyncio.to_thread(db.update_avatar_set, set_id, result["status"], result)
            record.update(status=result["status"], assets=result)
    if record["status"] == "ready":
        return await asyncio.to_thread(signed_assets, record)
    return {"id": set_id, "status": record["status"], "avatar_count": 11}


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
            import websockets
            async with websockets.connect(
                url.replace("https://", "wss://") + f"/ws/converse?mode=intake&voice={voice}",
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
