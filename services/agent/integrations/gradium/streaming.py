"""Bidirectional audio streaming helpers.

Async generators over Gradium's streaming speech endpoints — audio chunks out for synthesis,
transcript text out for recognition. These are the low-level building blocks a future realtime
`/voice/stream` WebSocket route will bridge to the browser; nothing consumes them yet, so they
sit beneath the sync REST seams (client.py) rather than alongside them. Unlike those seams they
raise on a server error line — an exception is how an async iterator reports a broken stream —
but they still short-circuit to an empty stream when no key is configured (the consuming route
is expected to key-guard first).
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from core.config import settings
from integrations.gradium.text_to_speech import DEFAULT_VOICE_ID

# Gradium caps a speech session at 300s; bound the stream to the same ceiling.
_STREAM_TIMEOUT_S = 300.0

_ASR_PATH = "/post/speech/asr"
_TTS_PATH = "/post/speech/tts"


async def stream_tts_audio(
    text: str,
    *,
    voice_id: str = DEFAULT_VOICE_ID,
    output_format: str = "pcm",
    http_client: httpx.AsyncClient | None = None,
) -> AsyncIterator[bytes]:
    """Stream synthesized audio for `text` chunk by chunk as Gradium produces it.

    `only_audio=False` selects the line-delimited JSON transport, so audio arrives as a
    sequence of base64 messages instead of one buffered body — the shape a realtime route
    forwards to the browser as it plays.
    """
    if not settings.gradium_api_key:
        return
    url = f"{settings.gradium_base_url.rstrip('/')}{_TTS_PATH}"
    headers = {"x-api-key": settings.gradium_api_key}
    body = {"text": text, "voice_id": voice_id, "output_format": output_format, "only_audio": False}
    async with _stream(http_client, url=url, headers=headers, json=body) as response:
        response.raise_for_status()
        async for message in _iter_messages(response):
            kind = message.get("type")
            if kind == "audio":
                yield base64.b64decode(message["audio"])
            elif kind == "end_of_stream":
                return


async def stream_stt_text(
    audio: bytes | AsyncIterator[bytes],
    *,
    language: str = "en",
    content_type: str = "audio/wav",
    http_client: httpx.AsyncClient | None = None,
) -> AsyncIterator[str]:
    """Stream transcript text out as Gradium recognizes `audio`.

    Gradium's REST ASR takes the clip as one body, so an async chunk source is drained first;
    true chunk-in streaming is WebSocket-only. What streams here is the transcript: text
    segments are yielded as their newline-delimited messages arrive.
    """
    if not settings.gradium_api_key:
        return
    body = bytes(audio) if isinstance(audio, (bytes, bytearray)) else await _drain(audio)
    url = f"{settings.gradium_base_url.rstrip('/')}{_ASR_PATH}"
    headers = {"x-api-key": settings.gradium_api_key, "Content-Type": content_type}
    params = {"json_config": json.dumps({"language": language})}
    async with _stream(http_client, url=url, headers=headers, params=params, content=body) as response:
        response.raise_for_status()
        async for message in _iter_messages(response):
            if message.get("type") == "text" and message.get("text"):
                yield message["text"]


@asynccontextmanager
async def _stream(http_client: httpx.AsyncClient | None, **request: object) -> AsyncIterator[httpx.Response]:
    # Reuse an injected client when present (tests); its lifetime belongs to the caller, so
    # only the per-request stream context is entered here, never the client itself.
    if http_client is not None:
        async with http_client.stream("POST", **request) as response:
            yield response
    else:
        async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT_S) as client:
            async with client.stream("POST", **request) as response:
                yield response


async def _iter_messages(response: httpx.Response) -> AsyncIterator[dict]:
    """Yield each newline-delimited JSON message, raising on a Gradium error line."""
    async for line in response.aiter_lines():
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("type") == "error":
            raise RuntimeError(message.get("message") or "Gradium stream error")
        yield message


async def _drain(chunks: AsyncIterator[bytes]) -> bytes:
    buffer = bytearray()
    async for chunk in chunks:
        buffer.extend(chunk)
    return bytes(buffer)
