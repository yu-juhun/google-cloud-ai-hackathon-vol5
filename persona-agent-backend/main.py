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
        location=os.environ.get("VERTEX_LOCATION", "global"),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "persona-agent-backend", "status": "healthy"}


@app.websocket("/ws/converse")
async def converse(websocket: WebSocket) -> None:
    await websocket.accept()
    conversation = LiveConversation(genai_client=_build_genai_client())
    await conversation.start()

    try:
        while True:
            message = await websocket.receive_json()

            if message.get("type") == "audio_chunk":
                audio_bytes = base64.b64decode(message["data"])
                await conversation.send_audio(audio_bytes)

                async for audio_out, _transcript in conversation.receive_audio_chunks():
                    if audio_out is not None:
                        await websocket.send_json(
                            {"type": "audio_chunk", "data": base64.b64encode(audio_out).decode("ascii")}
                        )

            elif message.get("type") == "finish":
                persona = await conversation.finish()
                await websocket.send_json({"type": "persona_result", "data": persona.model_dump()})
                break

    except WebSocketDisconnect:
        pass
