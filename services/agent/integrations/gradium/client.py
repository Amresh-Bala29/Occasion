"""Gradium API client.

A thin adapter over Gradium's REST speech endpoints: transcription (speech-to-text) and
synthesis (text-to-speech). Both normalize into our own result models, keeping Gradium's
`x-api-key` auth, base URL, and wire format in this one place. The client is sync and
blocking by design — async callers offload it (the /voice route uses run_in_threadpool),
matching the rest of the service. Failures come back as honest results, never raised.
"""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel

from core.config import settings

# A single short clip transcribes or synthesizes well within a minute either way.
_REQUEST_TIMEOUT_S = 60.0

# REST paths under settings.gradium_base_url (https://api.gradium.ai/api).
_ASR_PATH = "/post/speech/asr"
_TTS_PATH = "/post/speech/tts"


class TranscriptionResult(BaseModel):
    """The honest result of one speech-to-text request.

    `succeeded` is the field to branch on; `text` holds the transcript when it did and
    `error` explains why when it didn't. `status` is "completed" or "error".
    """

    succeeded: bool
    status: str
    text: str | None = None
    error: str | None = None


class SpeechResult(BaseModel):
    """The honest result of one text-to-speech request.

    On success `audio` carries the raw bytes and `media_type` names their format so the
    caller can serve or play them; on failure `error` explains why.
    """

    succeeded: bool
    status: str
    audio: bytes | None = None
    media_type: str | None = None
    error: str | None = None


class GradiumClient:
    """Runs speech-to-text and text-to-speech requests against Gradium's REST API."""

    def __init__(self, api_key: str, base_url: str, http_client: httpx.Client | None = None) -> None:
        # `http_client` is an injection seam for tests; production calls open a client per request.
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http = http_client

    @classmethod
    def from_settings(cls) -> "GradiumClient":
        """Build a client from configured credentials."""
        return cls(settings.gradium_api_key, settings.gradium_base_url)

    def transcribe(
        self,
        audio: bytes,
        *,
        content_type: str = "audio/wav",
        json_config: dict | None = None,
    ) -> TranscriptionResult:
        """Transcribe one audio clip to text.

        The audio is the raw request body (Gradium's REST ASR contract), its codec named by
        `content_type`; `json_config` (language and the like) rides along as a query param.
        The reply is newline-delimited JSON — text segments plus a possible error line.
        """
        headers = {"x-api-key": self._api_key, "Content-Type": content_type}
        params = {"json_config": json.dumps(json_config)} if json_config else None
        try:
            response = self._send(
                url=f"{self._base_url}{_ASR_PATH}", headers=headers, params=params, content=audio
            )
        except Exception as exc:  # transport failure or HTTP error status
            return TranscriptionResult(succeeded=False, status="error", error=_error_message(exc))
        return _transcription_from_ndjson(response.text)

    def synthesize(self, text: str, *, voice_id: str, output_format: str) -> SpeechResult:
        """Synthesize speech for `text` in the given voice and audio format.

        `only_audio` asks Gradium for the finished bytes directly rather than a JSON stream,
        so the response body is the clip itself.
        """
        headers = {"x-api-key": self._api_key}
        body = {"text": text, "voice_id": voice_id, "output_format": output_format, "only_audio": True}
        try:
            response = self._send(url=f"{self._base_url}{_TTS_PATH}", headers=headers, json=body)
        except Exception as exc:  # transport failure or HTTP error status
            return SpeechResult(succeeded=False, status="error", error=_error_message(exc))
        return SpeechResult(
            succeeded=True,
            status="completed",
            audio=response.content,
            media_type=_media_type_for(output_format),
        )

    def _send(self, **request: object) -> httpx.Response:
        # Reuse an injected client when present (tests), else open one bounded by the timeout.
        if self._http is not None:
            response = self._http.post(**request)
        else:
            with httpx.Client(timeout=_REQUEST_TIMEOUT_S) as client:
                response = client.post(**request)
        response.raise_for_status()
        return response


def _transcription_from_ndjson(payload: str) -> TranscriptionResult:
    segments: list[str] = []
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue  # ignore anything that isn't a JSON message
        if message.get("type") == "error":
            return TranscriptionResult(
                succeeded=False, status="error", error=_as_optional_str(message.get("message"))
            )
        if message.get("type") == "text":
            piece = _as_optional_str(message.get("text"))
            if piece:
                segments.append(piece.strip())
    # Segments arrive word by word without surrounding spaces, so join on a single space.
    text = " ".join(piece for piece in segments if piece)
    return TranscriptionResult(succeeded=True, status="completed", text=text)


def _error_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    # httpx.HTTPStatusError carries the response; prefix the status so 401/500 read clearly.
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code is not None:
        message = f"HTTP {status_code}: {message}"
    return message


def _media_type_for(output_format: str) -> str:
    if output_format == "wav":
        return "audio/wav"
    if output_format == "opus":
        return "audio/ogg"
    # Raw PCM and its sample-rate variants have no container; hand back opaque bytes.
    return "application/octet-stream"


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)
