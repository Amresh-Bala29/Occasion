"""Voice routes — speech-to-text and text-to-speech over Gradium."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse

from core.config import settings
from integrations.gradium.client import TranscriptionResult
from integrations.gradium.speech_to_text import TranscribeRequest, transcribe_audio
from integrations.gradium.streaming import stream_tts_audio
from integrations.gradium.text_to_speech import DEFAULT_VOICE_ID, SpeakRequest, synthesize_speech

router = APIRouter()


@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe(request: Request) -> TranscriptionResult:
    """Transcribe a posted audio clip (raw body) to text.

    The clip is the request body and its codec is the Content-Type header, matching Gradium's
    own ASR contract. A missing key or a Gradium failure comes back as succeeded=False rather
    than a 500.
    """
    audio = await request.body()
    content_type = request.headers.get("content-type") or "audio/wav"
    # The Gradium call blocks on HTTP; keep the event loop free.
    return await run_in_threadpool(
        transcribe_audio, audio, TranscribeRequest(content_type=content_type)
    )


@router.post("/speak")
async def speak(request: SpeakRequest) -> Response:
    """Synthesize speech and return the audio bytes to play.

    Success is binary, so unlike the rest of the service this endpoint can't hand back the
    result model: it returns the audio with its media type, or a JSON 502 carrying the error.
    """
    result = await run_in_threadpool(synthesize_speech, request)
    if not result.succeeded:
        return JSONResponse(status_code=502, content={"status": result.status, "error": result.error})
    return Response(content=result.audio, media_type=result.media_type or "audio/wav")


@router.post("/speak/stream")
async def speak_stream(request: SpeakRequest) -> Response:
    """Synthesize speech and stream audio chunks as Gradium produces them.

    The chunked twin of /speak, for callers that start playback before synthesis
    finishes. The key guard runs here (the generator's contract expects it); an
    error mid-stream drops the connection, which is the honest signal a stream has.
    """
    if not settings.gradium_api_key:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "error": "GRADIUM_API_KEY is not configured; set it in services/agent/.env"},
        )
    output_format = request.output_format or "wav"
    return StreamingResponse(
        stream_tts_audio(request.text, voice_id=request.voice_id or DEFAULT_VOICE_ID, output_format=output_format),
        media_type=f"audio/{output_format}",
    )
