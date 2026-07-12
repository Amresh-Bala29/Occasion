"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Records one voice clip and hands it back as 16-bit PCM WAV.
 *
 * Gradium's STT accepts wav/pcm/ogg-opus but not webm — the only container
 * Chrome's MediaRecorder produces — so stop() decodes the recording with
 * WebAudio and re-encodes it as WAV before returning. Clips are short, so the
 * in-browser transcode stays cheap.
 */
export function useVoice() {
  const [supported, setSupported] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // Computed after mount so the server render and first client render agree.
  useEffect(() => {
    setSupported("MediaRecorder" in window && Boolean(navigator.mediaDevices?.getUserMedia));
  }, []);

  useEffect(() => () => releaseRecorder(recorderRef), []);

  async function start() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferred = "audio/webm;codecs=opus";
      const recorder = MediaRecorder.isTypeSupported(preferred)
        ? new MediaRecorder(stream, { mimeType: preferred })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setError("Microphone access was denied or unavailable.");
    }
  }

  function stop(): Promise<Blob | null> {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      setRecording(false);
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      recorder.onstop = async () => {
        recorder.stream.getTracks().forEach((track) => track.stop()); // release the mic light
        recorderRef.current = null;
        setRecording(false);
        const recorded = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        chunksRef.current = [];
        if (recorded.size === 0) {
          resolve(null);
          return;
        }
        try {
          resolve(await toWav(recorded));
        } catch {
          setError("Could not process the recording.");
          resolve(null);
        }
      };
      recorder.stop();
    });
  }

  return { supported, recording, start, stop, error } as const;
}

async function toWav(recorded: Blob): Promise<Blob> {
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(await recorded.arrayBuffer());
    return encodeWav(decoded);
  } finally {
    void context.close();
  }
}

function encodeWav(audio: AudioBuffer): Blob {
  // Mono 16-bit PCM with the canonical 44-byte RIFF header.
  const samples = mixToMono(audio);
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeAscii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, audio.sampleRate, true);
  view.setUint32(28, audio.sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeAscii(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

function mixToMono(audio: AudioBuffer): Float32Array {
  if (audio.numberOfChannels === 1) return audio.getChannelData(0);
  const mixed = new Float32Array(audio.length);
  for (let channel = 0; channel < audio.numberOfChannels; channel++) {
    const data = audio.getChannelData(channel);
    for (let i = 0; i < audio.length; i++) mixed[i] += data[i] / audio.numberOfChannels;
  }
  return mixed;
}

function releaseRecorder(ref: { current: MediaRecorder | null }) {
  const recorder = ref.current;
  if (!recorder) return;
  if (recorder.state !== "inactive") recorder.stop();
  recorder.stream.getTracks().forEach((track) => track.stop());
  ref.current = null;
}
