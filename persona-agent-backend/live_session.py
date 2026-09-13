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
  real method is `send(input=..., end_of_turn=...)`. Task 6 must be written
  against `send()`, not `send_realtime_input()`. This is a real
  discrepancy from the spec's assumed name and needs a human decision
  before Task 6 proceeds.
"""
