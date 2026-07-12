"""Tests for the Gradium voice integration (speech-to-text + text-to-speech).

Gradium is never called for real here — an httpx MockTransport stands in for its REST API, so
these tests assert how we shape requests (x-api-key, endpoints, body/params) and normalize the
ndjson/audio replies into honest results. The entry seams are exercised through the same seam a
route uses, and the route tests fake the seams and drive the app with TestClient.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from integrations.gradium.client import GradiumClient, SpeechResult, TranscriptionResult  # noqa: E402
from integrations.gradium.speech_to_text import TranscribeRequest, transcribe_audio  # noqa: E402
from integrations.gradium.streaming import stream_stt_text, stream_tts_audio  # noqa: E402
from integrations.gradium.text_to_speech import SpeakRequest, synthesize_speech  # noqa: E402
from main import app  # noqa: E402


def client_with(handler) -> GradiumClient:
    """A GradiumClient whose HTTP calls are answered by `handler` instead of the network."""
    transport = httpx.MockTransport(handler)
    return GradiumClient(api_key="gd-test", base_url="https://api.test/api", http_client=httpx.Client(transport=transport))


# --- Client: text-to-speech ---


def test_synthesize_returns_audio() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"RIFFfake-wav-bytes")

    result = client_with(respond).synthesize("Hello", voice_id="v1", output_format="wav")

    assert result.succeeded is True
    assert result.status == "completed"
    assert result.audio == b"RIFFfake-wav-bytes"
    assert result.media_type == "audio/wav"
    request = seen[0]
    assert str(request.url) == "https://api.test/api/post/speech/tts"
    assert request.headers["x-api-key"] == "gd-test"
    assert json.loads(request.content) == {
        "text": "Hello",
        "voice_id": "v1",
        "output_format": "wav",
        "only_audio": True,
    }


def test_synthesize_http_error_is_failure() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error from server 1008: API key is revoked or expired")

    result = client_with(respond).synthesize("Hi", voice_id="v1", output_format="wav")

    assert result.succeeded is False
    assert result.status == "error"
    assert "500" in result.error


# --- Client: speech-to-text ---


def test_transcribe_joins_text_segments() -> None:
    seen: list[httpx.Request] = []
    ndjson = "\n".join(
        [
            json.dumps({"type": "text", "text": "hello"}),
            json.dumps({"type": "text", "text": "world"}),
            json.dumps({"type": "end_text", "stop_s": 1.2}),
        ]
    )

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=ndjson)

    result = client_with(respond).transcribe(
        b"audio-bytes", content_type="audio/wav", json_config={"language": "en"}
    )

    assert result.succeeded is True
    assert result.text == "hello world"
    request = seen[0]
    assert str(request.url).startswith("https://api.test/api/post/speech/asr")
    assert request.headers["x-api-key"] == "gd-test"
    assert request.headers["content-type"] == "audio/wav"
    assert request.content == b"audio-bytes"
    assert json.loads(request.url.params["json_config"]) == {"language": "en"}


def test_transcribe_error_line_is_failure() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=json.dumps({"type": "error", "message": "invalid audio format"}))

    result = client_with(respond).transcribe(b"bad", content_type="audio/wav")

    assert result.succeeded is False
    assert result.status == "error"
    assert result.error == "invalid audio format"


def test_from_settings_uses_configured_values(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gradium_api_key", "gd-abc")
    monkeypatch.setattr(settings, "gradium_base_url", "https://api.test/api/")
    client = GradiumClient.from_settings()

    assert client._api_key == "gd-abc"
    assert client._base_url == "https://api.test/api"  # trailing slash trimmed


# --- Entry seams: key-guard and forwarding ---


def test_transcribe_audio_requires_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gradium_api_key", "")

    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Gradium must not be called without a key")

    result = transcribe_audio(b"audio", client=client_with(boom))

    assert result.succeeded is False
    assert result.status == "error"
    assert "GRADIUM_API_KEY" in result.error


def test_synthesize_speech_requires_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gradium_api_key", "")

    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Gradium must not be called without a key")

    result = synthesize_speech(SpeakRequest(text="Hi"), client=client_with(boom))

    assert result.succeeded is False
    assert "GRADIUM_API_KEY" in result.error


def test_transcribe_audio_forwards_language(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gradium_api_key", "gd-test")
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=json.dumps({"type": "text", "text": "hi"}))

    result = transcribe_audio(b"audio", TranscribeRequest(language="fr"), client=client_with(respond))

    assert result.succeeded is True
    assert result.text == "hi"
    assert json.loads(seen[0].url.params["json_config"]) == {"language": "fr"}


# --- Route ---


def test_speak_endpoint_returns_audio(monkeypatch) -> None:
    def fake_synth(request: SpeakRequest) -> SpeechResult:
        assert request.text == "Hello"
        return SpeechResult(succeeded=True, status="completed", audio=b"AUDIO", media_type="audio/wav")

    monkeypatch.setattr("api.routes.voice.synthesize_speech", fake_synth)
    response = TestClient(app).post("/voice/speak", json={"text": "Hello"})

    assert response.status_code == 200
    assert response.content == b"AUDIO"
    assert response.headers["content-type"] == "audio/wav"


def test_speak_endpoint_reports_failure(monkeypatch) -> None:
    def fake_synth(request: SpeakRequest) -> SpeechResult:
        return SpeechResult(
            succeeded=False,
            status="error",
            error="GRADIUM_API_KEY is not configured; set it in services/agent/.env",
        )

    monkeypatch.setattr("api.routes.voice.synthesize_speech", fake_synth)
    response = TestClient(app).post("/voice/speak", json={"text": "Hello"})

    assert response.status_code == 502
    assert "GRADIUM_API_KEY" in response.json()["error"]


def test_speak_endpoint_rejects_empty_text() -> None:
    assert TestClient(app).post("/voice/speak", json={"text": ""}).status_code == 422


def test_transcribe_endpoint_returns_transcript(monkeypatch) -> None:
    def fake_transcribe(audio: bytes, request: TranscribeRequest) -> TranscriptionResult:
        assert audio == b"clip"
        assert request.content_type == "audio/wav"
        return TranscriptionResult(succeeded=True, status="completed", text="hello there")

    monkeypatch.setattr("api.routes.voice.transcribe_audio", fake_transcribe)
    response = TestClient(app).post("/voice/transcribe", content=b"clip", headers={"content-type": "audio/wav"})

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is True
    assert body["text"] == "hello there"


# --- Streaming helpers ---


def test_stream_tts_yields_audio_chunks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gradium_api_key", "gd-test")
    monkeypatch.setattr(settings, "gradium_base_url", "https://api.test/api")
    ndjson = "\n".join(
        [
            json.dumps({"type": "audio", "audio": base64.b64encode(b"pcmpcm").decode()}),
            json.dumps({"type": "end_of_stream"}),
        ]
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=ndjson)

    async def collect() -> list[bytes]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            return [chunk async for chunk in stream_tts_audio("hi", http_client=client)]
        finally:
            await client.aclose()

    assert asyncio.run(collect()) == [b"pcmpcm"]


def test_stream_stt_yields_text(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gradium_api_key", "gd-test")
    monkeypatch.setattr(settings, "gradium_base_url", "https://api.test/api")
    ndjson = "\n".join(
        [json.dumps({"type": "text", "text": "hello"}), json.dumps({"type": "text", "text": "world"})]
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=ndjson)

    async def collect() -> list[str]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            return [text async for text in stream_stt_text(b"audio", http_client=client)]
        finally:
            await client.aclose()

    assert asyncio.run(collect()) == ["hello", "world"]


def test_stream_tts_without_key_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gradium_api_key", "")

    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call Gradium without a key")

    async def collect() -> list[bytes]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
        try:
            return [chunk async for chunk in stream_tts_audio("hi", http_client=client)]
        finally:
            await client.aclose()

    assert asyncio.run(collect()) == []
