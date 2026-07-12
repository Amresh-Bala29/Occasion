"use client";

import { useState } from "react";

import { useVoice } from "@/hooks/useVoice";
import { transcribeAudio } from "@/lib/api";

interface VoiceAssistantProps {
  onTranscript: (text: string) => void;
}

/** Mic toggle for the task form: record, transcribe, hand the text to the composer. */
export function VoiceAssistant({ onTranscript }: VoiceAssistantProps) {
  const { supported, recording, start, stop, error: recordError } = useVoice();
  const [transcribing, setTranscribing] = useState(false);
  const [transcribeError, setTranscribeError] = useState("");

  async function handleToggle() {
    setTranscribeError("");
    if (!recording) {
      await start();
      return;
    }
    const clip = await stop();
    if (!clip) return;
    setTranscribing(true);
    try {
      const result = await transcribeAudio(clip);
      if (result.succeeded && result.text) {
        onTranscript(result.text);
      } else {
        setTranscribeError(result.error ?? "Transcription came back empty.");
      }
    } catch (error) {
      setTranscribeError(error instanceof Error ? error.message : String(error));
    } finally {
      setTranscribing(false);
    }
  }

  // No button during SSR or in browsers without MediaRecorder.
  if (!supported) return null;

  const errorMessage = transcribeError || recordError;

  return (
    <>
      {errorMessage && <span className="text-[12px] leading-normal text-danger">{errorMessage}</span>}
      <button
        type="button"
        className="btn btn-secondary inline-flex items-center gap-2"
        onClick={() => void handleToggle()}
        disabled={transcribing}
        aria-pressed={recording}
      >
        {transcribing ? (
          <>
            <span
              className="size-3 animate-spin rounded-full border-2 border-brand-mist border-t-brand"
              aria-hidden="true"
            />
            Transcribing…
          </>
        ) : recording ? (
          <>
            <span className="dot animate-pulse bg-danger" aria-hidden="true" />
            Stop
          </>
        ) : (
          <>
            <span className="dot dot-gray" aria-hidden="true" />
            Speak
          </>
        )}
      </button>
    </>
  );
}
