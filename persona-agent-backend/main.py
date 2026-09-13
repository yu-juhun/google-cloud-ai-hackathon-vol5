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

            elif message.get("type") == "finish":
                relay_task.cancel()
                try:
                    await relay_task
                except asyncio.CancelledError:
                    pass
                persona = await conversation.finish()
                await websocket.send_json({"type": "persona_result", "data": persona.model_dump()})
                break

    except WebSocketDisconnect:
        relay_task.cancel()
    finally:
        if not relay_task.done():
            relay_task.cancel()
