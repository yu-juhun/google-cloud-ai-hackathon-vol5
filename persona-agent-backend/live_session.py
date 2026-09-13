# persona-agent-backend/live_session.py
"""
SDK verification (google-genai==1.5.0), recorded 2026-09-13:
- client.aio.live.connect(model=..., config=...) is an async context manager
  yielding a `google.genai.live.AsyncSession` object. Confirmed via
  `help(client.aio.live.connect)` and by reading
  google/genai/live.py in the installed package.

- Session send method:
  `async def send(self, *, input=None, end_of_turn=False)`
  There is NO `send_realtime_input` method on AsyncSession in this version.
  `input` accepts a ContentListUnion/dict, a LiveClientContentOrDict,
  a LiveClientRealtimeInputOrDict, a LiveClientToolResponseOrDict, or a
  FunctionResponseOrDict/Sequence thereof. For streaming raw audio chunks,
  the pattern used internally (see `_send_loop`) is:
      await session.send(input={'data': audio_bytes, 'mimeType': 'audio/pcm'})
  There is also a higher-level `async def start_stream(self, *, stream:
  AsyncIterator[bytes], mime_type: str) -> AsyncIterator[LiveServerMessage]`
  that spawns its own send/receive loop over an async byte-chunk generator
  and yields server messages directly (an alternative to calling
  send()/receive() manually).

- Session receive method:
  `async def receive(self) -> AsyncIterator[types.LiveServerMessage]`
  (matches the design's `.receive()` assumption exactly). It is an async
  generator yielding `LiveServerMessage` objects, one per server message,
  and stops (after yielding the final one) once
  `result.server_content.turn_complete` is true. Each `LiveServerMessage`
  exposes both `.data` (convenience accessor for raw audio bytes, if the
  message contains inline audio) and `.text` (convenience accessor for any
  text/transcript content), plus the full `.server_content` structure — so
  a single receive() message can carry audio, text, or both depending on
  what the model sent for that turn.

- How to end a session:
  AsyncSession has an explicit `async def close(self)` method, which closes
  the underlying websocket (`await self._ws.close()`). Exiting the
  `async with client.aio.live.connect(...) as session:` block also closes
  the session (the context manager's __aexit__ calls close()), so relying on
  the `async with` block is sufficient — no separate explicit close() call
  is required unless the session is kept open outside a `with` block.

Design-spec comparison:
- `.receive()` matches exactly.
- `send_realtime_input` does NOT exist on the installed AsyncSession; the
  real method is `send(input=..., end_of_turn=...)`. Task 6 was written
  against `send()`, not `send_realtime_input()`, per this recorded
  discrepancy.
"""
from google.genai import types

from keyword_inference import infer_keywords
from persona_extraction import extract_persona
from schemas import Persona

SYSTEM_PROMPT = """\
あなたは、車椅子ユーザーやその家族の旅行・外食プランニングを手伝うアシスタントです。
ユーザーの移動の制約、食事の制約、今日の目的、同行者、優先したいことを、
自然な会話で聞き出してください。一度に多くの質問をせず、相手の話を踏まえて
一つずつ掘り下げてください。
"""


class LiveConversation:
    def __init__(self, genai_client):
        self.genai_client = genai_client
        self._session = None
        self._session_ctx = None
        self._transcript_parts: list[str] = []

    async def start(self) -> None:
        self._session_ctx = self.genai_client.aio.live.connect(
            model="gemini-2.5-flash-native-audio-preview",
            config=types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=SYSTEM_PROMPT,
                output_audio_transcription={},
                input_audio_transcription={},
            ),
        )
        self._session = await self._session_ctx.__aenter__()

    async def send_audio(self, chunk: bytes) -> None:
        await self._session.send(
            input={"data": chunk, "mimeType": "audio/pcm;rate=16000"},
            end_of_turn=False,
        )

    async def receive_audio_chunks(self):
        """Async generator yielding (audio_bytes | None, transcript_text | None) pairs."""
        async for message in self._session.receive():
            audio_bytes = None
            transcript_text = None
            if message.data:
                audio_bytes = message.data
            if message.server_content and message.server_content.output_transcription:
                transcript_text = message.server_content.output_transcription.text
                self._transcript_parts.append(f"モデル: {transcript_text}")
            if message.server_content and message.server_content.input_transcription:
                user_text = message.server_content.input_transcription.text
                self._transcript_parts.append(f"ユーザー: {user_text}")
            yield audio_bytes, transcript_text

    async def finish(self) -> Persona:
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(None, None, None)
        transcript = "\n".join(self._transcript_parts)
        persona = extract_persona(transcript=transcript, genai_client=self.genai_client)
        return infer_keywords(persona, self.genai_client)
