from datetime import timedelta
from types import SimpleNamespace

import pytest
from google.genai import types
from michibiki import db
from michibiki import experience_images as images
from sqlalchemy import create_engine


def test_empty_parts_are_not_a_type_error():
    response = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=None))]
    )
    with pytest.raises(images.NoImageReturned):
        images.extract_image(response)


def test_blocked_image_is_not_retried():
    response = types.GenerateContentResponse(
        candidates=[types.Candidate(finish_reason="SAFETY")]
    )
    with pytest.raises(images.ImageBlocked):
        images.extract_image(response)


def test_shared_model_windows(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'quota.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    timestamp = db.now()
    monkeypatch.setattr(db, "now", lambda: timestamp)
    db.migrate(engine)
    models = ["primary", "fallback"]
    assert [db.reserve_image_request(models)[0] for _ in range(4)] == [
        "primary",
        "primary",
        "fallback",
        "fallback",
    ]
    assert db.reserve_image_request(models) == (None, 61)
    timestamp += timedelta(seconds=62)
    assert db.reserve_image_request(models) == ("primary", 0)
    db.defer_image_model("primary")
    assert db.reserve_image_request(models) == ("fallback", 0)
    engine.dispose()


def test_rolling_window_does_not_reset_both_slots(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'rolling.db'}")
    monkeypatch.setattr(db, "engine", lambda: engine)
    timestamp = db.now()
    monkeypatch.setattr(db, "now", lambda: timestamp)
    db.migrate(engine)
    assert db.reserve_image_request(["primary"]) == ("primary", 0)
    timestamp += timedelta(seconds=20)
    assert db.reserve_image_request(["primary"]) == ("primary", 0)
    timestamp += timedelta(seconds=42)
    assert db.reserve_image_request(["primary"]) == ("primary", 0)
    assert db.reserve_image_request(["primary"]) == (None, 19)
    engine.dispose()


@pytest.mark.asyncio
async def test_empty_response_then_image(monkeypatch):
    responses = iter(
        [
            types.GenerateContentResponse(
                candidates=[types.Candidate(content=types.Content(parts=None))]
            ),
            types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        content=types.Content(
                            parts=[
                                types.Part.from_bytes(
                                    data=b"image", mime_type="image/png"
                                )
                            ]
                        )
                    )
                ]
            ),
        ]
    )

    async def request(**kwargs):
        return next(responses)

    async def sleep(seconds):
        pass

    monkeypatch.setattr(db, "reserve_image_request", lambda models: (models[0], 0))
    monkeypatch.setattr(images.asyncio, "sleep", sleep)
    metadata = {}
    data = await images.image_call(
        SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=request))
        ),
        metadata=metadata,
        mission_id="test",
        ordinal=4,
        model="primary",
    )
    assert data.data == b"image" and metadata["attempts"] == 2
