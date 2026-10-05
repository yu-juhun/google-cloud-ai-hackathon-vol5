import json
from unittest.mock import MagicMock

from michibiki.video import check_relevance


def test_check_relevance_on_topic():
    fake_response = MagicMock()
    fake_response.text = json.dumps({"on_topic": True, "reason": ""})
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    on_topic, reason = check_relevance("入口は段差なし", "もっと穏やかな雰囲気で", fake_client)

    assert on_topic is True
    call_kwargs = fake_client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].response_mime_type == "application/json"


def test_check_relevance_off_topic():
    fake_response = MagicMock()
    fake_response.text = json.dumps({"on_topic": False, "reason": "体験談と無関係な話題です"})
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    on_topic, reason = check_relevance("入口は段差なし", "全く違うアニメの話をしてください", fake_client)

    assert on_topic is False
    assert reason == "体験談と無関係な話題です"


def test_check_relevance_defaults_to_rejecting_on_malformed_response():
    """A malformed classifier response must fail closed (reject), not open
    (silently let an unvalidated feedback through to Veo)."""
    fake_response = MagicMock()
    fake_response.text = "not json at all"
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    on_topic, reason = check_relevance("入口は段差なし", "何か", fake_client)

    assert on_topic is False


def test_check_relevance_fails_closed_on_string_on_topic():
    """A truthy-but-wrong-typed on_topic (e.g. the string "false") must not
    be coerced to True by Python truthiness; only an actual boolean True passes."""
    fake_response = MagicMock()
    fake_response.text = json.dumps({"on_topic": "false", "reason": ""})
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    on_topic, _ = check_relevance("入口は段差なし", "何か", fake_client)

    assert on_topic is False
