import asyncio
import base64
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google import genai

from live_session import LiveConversation

app = FastAPI(title="persona-agent-backend")


def _build_genai_client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=os.environ["VERTEX_PROJECT_ID"],
        location=os.environ.get("VERTEX_LOCATION", "us-central1"),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "persona-agent-backend", "status": "healthy"}


async def _relay_model_audio(websocket: WebSocket, conversation: LiveConversation) -> None:
    """Continuously forwards Live API audio/transcript output to the client.

    Runs as its own task for the whole session lifetime so that inbound
    audio_chunk messages never have to block waiting for a model turn to
    complete before the next inbound message (including `finish`) can be
    read.
    """
    async for audio_out, _transcript in conversation.receive_audio_chunks():
        if audio_out is not None:
            await websocket.send_json(
                {"type": "audio_chunk", "data": base64.b64encode(audio_out).decode("ascii")}
            )


@app.websocket("/ws/converse")
async def converse(websocket: WebSocket) -> None:
    await websocket.accept()
    conversation = LiveConversation(genai_client=_build_genai_client())
    await conversation.start()

    relay_task = asyncio.create_task(_relay_model_audio(websocket, conversation))

    try:
        while True:
            message = await websocket.receive_json()

            if message.get("type") == "audio_chunk":
                audio_bytes = base64.b64decode(message["data"])
                await conversation.send_audio(audio_bytes)

            elif message.get("type") == "avatar_photo":
                photo_bytes = base64.b64decode(message["data"])
                content_type = message.get("content_type", "image/png")
                try:
                    # set_base_photo calls YouCam synchronously (it can
                    # block for up to ~120s), so run it in a worker thread
                    # rather than blocking the event loop that this same
                    # connection's relay_task needs to keep relaying audio.
                    base_image, base_image_open = await asyncio.to_thread(
                        conversation.set_base_photo, photo_bytes=photo_bytes, content_type=content_type
                    )
                except Exception as e:
                    # A YouCam failure (bad credentials, no face detected,
                    # network error, poll timeout) must not kill the whole
                    # voice conversation — leave _base_avatar_image unset so
                    # finish() falls back to its no-photo behavior.
                    await websocket.send_json({"type": "avatar_error", "message": str(e)})
                else:
                    await websocket.send_json(
                        {
                            "type": "avatar_base_image",
                            "data": base64.b64encode(base_image).decode("ascii"),
                            "open_mouth_data": base64.b64encode(base_image_open).decode("ascii"),
                        }
                    )

            elif message.get("type") == "finish":
                relay_task.cancel()
                try:
                    await relay_task
                except asyncio.CancelledError:
                    pass
                persona, avatar_image, avatar_image_open = await conversation.finish()
                persona_data = persona.model_dump()
                persona_data["avatar_image"] = (
                    base64.b64encode(avatar_image).decode("ascii") if avatar_image is not None else None
                )
                persona_data["avatar_image_open"] = (
                    base64.b64encode(avatar_image_open).decode("ascii") if avatar_image_open is not None else None
                )
                await websocket.send_json({"type": "persona_result", "data": persona_data})
                break

    except WebSocketDisconnect:
        relay_task.cancel()
        await conversation.close()
    finally:
        if not relay_task.done():
            relay_task.cancel()
