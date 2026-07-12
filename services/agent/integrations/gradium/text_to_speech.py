"""Text-to-speech synthesis via Gradium.

The reusable seam the /voice route calls: guard on the configured key, then ask the Gradium
client to synthesize speech and return the audio as an honest result.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.config import settings
from integrations.gradium.client import GradiumClient, SpeechResult

# An English flagship voice (Zoey) from Gradium's catalog; callers may override per request.
DEFAULT_VOICE_ID = "NbpkqMVS3CJeq2j8"
# WAV is self-describing and browser-playable, unlike raw PCM.
DEFAULT_OUTPUT_FORMAT = "wav"


class SpeakRequest(BaseModel):
    """Text to voice, and how."""

    text: str = Field(..., min_length=1, description="What to say, in plain language.")
    voice_id: str = Field(DEFAULT_VOICE_ID, description="Gradium voice id to speak in.")
    output_format: str = Field(DEFAULT_OUTPUT_FORMAT, description="Audio container/codec to return.")


def synthesize_speech(request: SpeakRequest, client: GradiumClient | None = None) -> SpeechResult:
    """Synthesize speech for the request through Gradium and return the audio.

    Blocking: opens an HTTP request to Gradium, so async callers must offload it.
    """
    if not settings.gradium_api_key:
        return SpeechResult(
            succeeded=False,
            status="error",
            error="GRADIUM_API_KEY is not configured; set it in services/agent/.env",
        )
    runner = client or GradiumClient.from_settings()
    return runner.synthesize(
        request.text, voice_id=request.voice_id, output_format=request.output_format
    )
