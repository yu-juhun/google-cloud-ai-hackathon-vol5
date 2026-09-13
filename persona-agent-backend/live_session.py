# persona-agent-backend/live_session.py
"""
SDK verification, updated 2026-09-13 during Task 6 Step 7 human smoke test.

Original Task 5 verification was done against google-genai==1.5.0, which
predates several Live API features this design needs. Running the real
end-to-end smoke test surfaced three real defects, all fixed here and in
main.py/requirements.txt:

1. **google-genai was too old.** 1.5.0 has no
   `input_audio_transcription`/`output_audio_transcription` fields on
   `LiveConnectConfig` at all (`extra_forbidden` validation error) — the
   transcription feature this design depends on didn't exist yet. Upgraded
   to google-genai==2.23.0 (latest at the time), which has both fields.

2. **Model name was wrong.** `gemini-2.5-flash-native-audio-preview` does
   not exist as a Vertex AI publisher model. Verified the real available
   model via `client.models.list()`: `gemini-live-2.5-flash-native-audio`.

3. **`send()` is deprecated and doesn't reach the VAD audio pipeline.**
   In google-genai==2.23.0, `AsyncSession.send()` still exists but is
   deprecated, and — confirmed empirically — sending raw audio through it
   never triggers a model response (no messages ever come back from
   `receive()`), because it goes through the generic client-content path,
   not the realtime-audio/VAD path. The current, working method is:
       await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
   Verified working end-to-end with a text-turn probe (`send_client_content`)
   that produced a full response strea	m with `output_transcription` chunks
   and a final `turn_complete=True` message — confirming `receive()`'s
   shape and lifecycle exactly as this file already assumed.

Also confirmed via manual probing (region matters for this model):
`location="global"` returns "Publisher model ... not found" for this model;
`location="us-central1"` connects successfully. main.py's default
VERTEX_LOCATION was changed from "global" to "us-central1" accordingly.

Everything else from the original verification still holds on 2.23.0:
- `client.aio.live.connect(model=..., config=...)` is an async context
  manager yielding an `AsyncSession`.
- `async def receive(self) -> AsyncIterator[types.LiveServerMessage]` is
  an async generator, one message per server event, ending after a message
  with `server_content.turn_complete=True`.
- Exiting the `async with ...connect(...) as session:` block closes the
  session; no separate explicit `close()` call is required.

Not yet verified end-to-end with real streamed microphone audio (only with
a synthetic tone, which the server-side VAD never recognized as speech, and
with a text-turn probe) — that verification is the human smoke test itself.
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
            model="gemini-live-2.5-flash-native-audio",
            config=types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=SYSTEM_PROMPT,
                output_audio_transcription={},
                input_audio_transcription={},
            ),
        )
        self._session = await self._session_ctx.__aenter__()

    async def send_audio(self, chunk: bytes) -> None:
        await self._session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"),
        )

    async def receive_audio_chunks(self):
        """Async generator yielding (audio_bytes | None, transcript_text | None) pairs.

        `session.receive()` itself only covers ONE model turn — its
        underlying implementation breaks out of its loop as soon as it sees
        a turn-complete message (confirmed by reading
        google/genai/live.py's AsyncSession.receive source). A real
        multi-turn conversation needs a new receive() call per turn, so this
        wraps it in an outer loop that keeps calling receive() again for
        each subsequent turn until the caller cancels this generator
        (main.py cancels the task that drives this when `finish` arrives).
        """
        while True:
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

    async def close(self) -> None:
        """Closes the underlying Live API session without running extraction.

        Used when the client disconnects (e.g. a page reload) without ever
        sending `finish` — without this, the Live API session is left open
        on the server indefinitely.
        """
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(None, None, None)
            self._session_ctx = None

    async def finish(self) -> Persona:
        await self.close()
        transcript = "\n".join(self._transcript_parts)
        persona = extract_persona(transcript=transcript, genai_client=self.genai_client)
        return infer_keywords(persona, self.genai_client)
