from unittest.mock import Mock

import pytest

from app.recommandations import mistral_client


def _failing_client(message: str) -> Mock:
    client = Mock()
    client.chat.complete.side_effect = RuntimeError(message)
    client.embeddings.create.side_effect = RuntimeError(message)
    return client


def test_chat_capacity_exceeded_fails_immediately(monkeypatch):
    client = _failing_client(
        "Status 429: Service tier capacity exceeded for this model "
        "(request_tier_capacity_exceeded, code 3505)"
    )
    sleep = Mock()
    monkeypatch.setattr(mistral_client, "get_client", lambda: client)
    monkeypatch.setattr(mistral_client.time, "sleep", sleep)

    with pytest.raises(RuntimeError, match="Echec appel Mistral"):
        mistral_client.chat_json("system", "user", max_retries=2)

    assert client.chat.complete.call_count == 1
    sleep.assert_not_called()


def test_last_retry_does_not_sleep(monkeypatch):
    client = _failing_client("Status 429: rate limit exceeded")
    sleep = Mock()
    monkeypatch.setattr(mistral_client, "get_client", lambda: client)
    monkeypatch.setattr(mistral_client.time, "sleep", sleep)

    with pytest.raises(RuntimeError, match="Echec appel Mistral"):
        mistral_client.chat_json("system", "user", max_retries=2)

    assert client.chat.complete.call_count == 2
    sleep.assert_called_once_with(20)


def test_embeddings_capacity_exceeded_fails_immediately(monkeypatch):
    client = _failing_client("request_tier_capacity_exceeded code 3505")
    sleep = Mock()
    monkeypatch.setattr(mistral_client, "get_client", lambda: client)
    monkeypatch.setattr(mistral_client.time, "sleep", sleep)

    with pytest.raises(RuntimeError, match="Echec appel Mistral"):
        mistral_client.embed_texts(["texte"], max_retries=3)

    assert client.embeddings.create.call_count == 1
    sleep.assert_not_called()
