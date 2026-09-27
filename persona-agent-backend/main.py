import asyncio
import base64
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google import genai

from live_session import VOICE_NAMES, LiveConversation
from youcam_client import VERIFIED_TEMPLATE_IDS, flatten_template_ids, load_avatar_template_catalog

app = FastAPI(title="persona-agent-backend")
logger = logging.getLogger(__name__)


def _build_genai_client() -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=os.environ["VERTEX_PROJECT_ID"],
        location=os.environ.get("VERTEX_LOCATION", "us-central1"),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "persona-agent-backend", "status": "healthy"}


def _template_catalog_with_fallback() -> dict:
    try:
        return load_avatar_template_catalog()
    except Exception as e:
        logger.warning("could not load avatar template catalog, falling back: %s", e)
        return {"": {"": [{"id": tid, "title": tid, "thumb": None} for tid in VERIFIED_TEMPLATE_IDS]}}


@app.get("/avatar-templates")
async def avatar_templates() -> dict:
    """A plain HTTP endpoint on purpose — the client needs this catalog
    before the user has chosen anything (gender/style/voice), and it has
    nothing to do with the Gemini Live session. Fetching it over the
    WebSocket would force connecting — and therefore starting the Live
    session with whatever voice was picked so far, or none — before the
    user has actually finished choosing a voice. Reads a pre-processed
    static snapshot (see youcam_client.load_avatar_template_catalog),
    not a live YouCam API call."""
    return await asyncio.to_thread(_template_catalog_with_fallback)


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
    # Voice is chosen before the Live session exists, so it travels as a
    # connect-time query param rather than a WebSocket message.
    requested_voice = websocket.query_params.get("voice")
    voice_name = requested_voice if requested_voice in VOICE_NAMES else None
    try:
        # A startup failure (bad Vertex credentials, an unavailable Live
        # API model, or an unsupported voice_name) must reach the client
        # as a message, not just a closed connection with no explanation.
        await conversation.start(voice_name=voice_name)
    except Exception as e:
        await websocket.send_json({"type": "start_error", "message": str(e)})
        await websocket.close()
        return

    relay_task = asyncio.create_task(_relay_model_audio(websocket, conversation))

    try:
        while True:
            try:
                # receive_json() runs json.loads() itself — a client
                # sending text that isn't even valid JSON raises
                # JSONDecodeError here, before the isinstance guard below
                # ever gets a chance to run.
                message = await websocket.receive_json()
            except ValueError as e:
                logger.warning("dropping invalid JSON message: %s", e)
                continue

            if not isinstance(message, dict):
                # A conforming client always sends a JSON object; a
                # non-object frame (e.g. a bare array or string) would
                # otherwise raise AttributeError on message.get() below
                # and kill the whole session over one bad frame.
                logger.warning("dropping non-object message: %r", message)
                continue

            if message.get("type") == "audio_chunk":
                try:
                    # A malformed audio_chunk frame (missing/invalid
                    # base64 data) must not kill a whole conversation —
                    # audio_chunk arrives every ~128ms, so one bad frame
                    # is expected to happen occasionally and should just
                    # be dropped, not lose everything transcribed so far.
                    audio_bytes = base64.b64decode(message["data"])
                except (KeyError, ValueError, TypeError) as e:
                    logger.warning("dropping malformed audio_chunk: %s", e)
                else:
                    await conversation.send_audio(audio_bytes)

            elif message.get("type") == "avatar_photo":
                try:
                    photo_bytes = base64.b64decode(message["data"])
                except (KeyError, ValueError, TypeError) as e:
                    await websocket.send_json({"type": "avatar_error", "message": str(e)})
                    continue
                content_type = message.get("content_type", "image/png")
                requested_template_id = message.get("template_id")
                # Silently fall back to the default rather than forwarding
                # an unverified template_id to YouCam (that's a real, paid
                # API call away from a 400) — the client is untrusted input.
                # Re-fetches the (cached) catalog rather than reusing a
                # value captured at connect time, so a template added to
                # YouCam's catalog after this process started is still
                # accepted without a restart.
                verified_template_ids = await asyncio.to_thread(
                    lambda: flatten_template_ids(_template_catalog_with_fallback())
                )
                template_id = (
                    requested_template_id if requested_template_id in verified_template_ids else None
                )
                try:
                    # set_base_photo calls YouCam synchronously (it can
                    # block for up to ~120s), so run it in a worker thread
                    # rather than blocking the event loop that this same
                    # connection's relay_task needs to keep relaying audio.
                    base_image, base_image_open = await asyncio.to_thread(
                        conversation.set_base_photo,
                        photo_bytes=photo_bytes,
                        content_type=content_type,
                        template_id=template_id,
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
                except Exception as e:
                    # relay_task can die on its own before finish is ever
                    # sent (e.g. the Live API connection dropping
                    # mid-conversation) — re-raising that here would skip
                    # the finish_error handling below entirely.
                    logger.warning("relay_task ended with an error before finish: %s", e)
                try:
                    # A persona-extraction/avatar Gemini call can fail
                    # (network error, malformed response) after audio
                    # relaying has already stopped; without this the
                    # client would get no response at all instead of a
                    # message it can show the user.
                    persona, avatar_image, avatar_image_open = await conversation.finish()
                except Exception as e:
                    await websocket.send_json({"type": "finish_error", "message": str(e)})
                else:
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
