"""Speech-to-text transcription via Gradium.

The reusable seam the /voice route calls: guard on the configured key, then hand a raw audio
clip to the Gradium client and return the transcript as an honest result.
"""

from __future__ import annotations

from pydantic import BaseModel

from core.config import settings
from integrations.gradium.client import GradiumClient, TranscriptionResult

# Gradium's REST ASR reads a WAV body by default and speaks five languages; English is ours.
DEFAULT_CONTENT_TYPE = "audio/wav"
DEFAULT_LANGUAGE = "en"


class TranscribeRequest(BaseModel):
    """How to interpret an audio clip. The bytes themselves are passed separately."""

    content_type: str = DEFAULT_CONTENT_TYPE
    language: str = DEFAULT_LANGUAGE


def transcribe_audio(
    audio: bytes,
    request: TranscribeRequest | None = None,
    client: GradiumClient | None = None,
) -> TranscriptionResult:
    """Transcribe one audio clip through Gradium and return the transcript.

    Blocking: opens an HTTP request to Gradium, so async callers must offload it.
    """
    if not settings.gradium_api_key:
        return TranscriptionResult(
            succeeded=False,
            status="error",
            error="GRADIUM_API_KEY is not configured; set it in services/agent/.env",
        )
    request = request or TranscribeRequest()
    runner = client or GradiumClient.from_settings()
    return runner.transcribe(
        audio, content_type=request.content_type, json_config={"language": request.language}
    )
