"use client";

import { useEffect, useState, type FormEvent } from "react";

import { runComputerUseTask } from "@/lib/api";
import type { SessionResult } from "@/types";

type Phase = "idle" | "running" | "done" | "error";

const TASK_PLACEHOLDER =
  "e.g. Find three caterers near Pier 27 in San Francisco that can plate dinner for 320 guests on Aug 6, and list per-person pricing.";

/** Header button that opens a dialog for running one computer-use task end to end. */
export function TalkToOccasion() {
  const [open, setOpen] = useState(false);
  const [task, setTask] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<SessionResult | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = task.trim();
    if (!trimmed || phase === "running") return;
    setPhase("running");
    setResult(null);
    setErrorMessage("");
    try {
      setResult(await runComputerUseTask(trimmed));
      setPhase("done");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
      setPhase("error");
    }
  }

  function resetToForm() {
    setPhase("idle");
    setResult(null);
    setErrorMessage("");
  }

  return (
    <>
      <button
        type="button"
        className="inline-flex cursor-pointer items-center gap-2 rounded-full bg-brand px-[18px] py-[9px] text-[13.5px] font-semibold whitespace-nowrap text-white hover:bg-brand-deep"
        onClick={() => setOpen(true)}
      >
        {phase === "running" ? (
          <span
            className="size-3 animate-spin rounded-full border-2 border-white/35 border-t-white"
            aria-hidden="true"
          />
        ) : (
          <span
            className="size-2 animate-pulse rounded-full bg-white shadow-[0_0_0_3px_rgba(255,255,255,0.28)]"
            aria-hidden="true"
          />
        )}
        Talk to Occasion
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-[rgba(15,23,42,0.44)] px-5 pt-[9vh] pb-5"
          onClick={() => setOpen(false)}
        >
          <div
            className="max-h-[82vh] w-[min(640px,100%)] overflow-y-auto rounded-2xl bg-surface shadow-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="talk-to-occasion-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3.5 px-6 pt-5">
              <div>
                <h2 className="text-[17px] font-bold" id="talk-to-occasion-title">
                  Talk to Occasion
                </h2>
                <p className="mt-1 text-[13px] text-ink-soft">
                  Give Occasion a research task to run on real websites.
                </p>
              </div>
              <button
                type="button"
                className="-mt-1 -mr-1.5 cursor-pointer rounded-md p-1 text-[20px] leading-none text-ink-faint hover:text-ink"
                aria-label="Close"
                onClick={() => setOpen(false)}
              >
                ×
              </button>
            </div>

            <div className="flex flex-col gap-3.5 px-6 pt-[18px] pb-[22px]">
              {(phase === "idle" || phase === "error") && (
                <TaskForm
                  task={task}
                  errorMessage={phase === "error" ? errorMessage : ""}
                  onTaskChange={setTask}
                  onSubmit={handleSubmit}
                />
              )}
              {phase === "running" && <RunningStatus task={task} />}
              {phase === "done" && result && (
                <RunResult result={result} onRunAnother={resetToForm} onClose={() => setOpen(false)} />
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

interface TaskFormProps {
  task: string;
  errorMessage: string;
  onTaskChange: (task: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

function TaskForm({ task, errorMessage, onTaskChange, onSubmit }: TaskFormProps) {
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3.5">
      {errorMessage && <ErrorBanner message={errorMessage} />}
      <label className="text-[13px] font-semibold" htmlFor="occasion-task">
        What should Occasion research?
      </label>
      <textarea
        id="occasion-task"
        className="min-h-24 w-full resize-y rounded-[10px] border border-line-strong bg-surface px-[13px] py-[11px] text-[13.5px] leading-normal text-ink placeholder:text-ink-faint focus:border-brand focus:shadow-[0_0_0_3px_var(--color-brand-soft)] focus:outline-none"
        value={task}
        onChange={(event) => onTaskChange(event.target.value)}
        placeholder={TASK_PLACEHOLDER}
        autoFocus
      />
      <p className="text-[12px] leading-normal text-ink-faint">
        Occasion runs this in a managed browser session and reports back with an answer plus a
        replayable agent view. Nothing is booked or purchased without your approval.
      </p>
      <div className="flex items-center justify-end gap-2.5">
        <button type="submit" className="btn btn-primary" disabled={!task.trim()}>
          Run task
        </button>
      </div>
    </form>
  );
}

function RunningStatus({ task }: { task: string }) {
  return (
    <div
      className="flex items-center gap-3 rounded-[10px] border border-brand-mist bg-brand-soft px-4 py-3.5"
      role="status"
    >
      <span
        className="size-[18px] shrink-0 animate-spin rounded-full border-[2.5px] border-brand-mist border-t-brand"
        aria-hidden="true"
      />
      <div>
        <p className="text-[13.5px] font-semibold">Occasion is working on it…</p>
        <p className="mt-0.5 text-[12.5px] text-ink-soft">
          Running “{truncate(task.trim())}” in a managed browser session. This can take a few
          minutes — leave this open or check back.
        </p>
      </div>
    </div>
  );
}

interface RunResultProps {
  result: SessionResult;
  onRunAnother: () => void;
  onClose: () => void;
}

function RunResult({ result, onRunAnother, onClose }: RunResultProps) {
  return (
    <>
      {!result.succeeded && (
        <ErrorBanner message={result.error ?? "The session finished without a successful outcome."} />
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip chip-gray">{result.status}</span>
        {result.outcome && <span className={outcomeChipClass(result.outcome)}>{result.outcome}</span>}
        {result.agent_view_url && (
          <a
            className="ml-auto text-[13px] font-semibold whitespace-nowrap text-brand hover:underline"
            href={result.agent_view_url}
            target="_blank"
            rel="noreferrer"
          >
            Open agent view ↗
          </a>
        )}
      </div>
      {result.answer && (
        <>
          <span className="eyebrow">Answer</span>
          <div className="max-h-[300px] overflow-y-auto rounded-[10px] border border-line bg-[#f7f9fd] px-[15px] py-[13px] text-[13.5px] leading-[1.6] break-words whitespace-pre-wrap">
            {result.answer}
          </div>
        </>
      )}
      {result.session_id && (
        <p className="font-mono text-[11px] text-ink-faint [overflow-wrap:anywhere]">
          Session {result.session_id}
        </p>
      )}
      <div className="flex items-center justify-end gap-2.5 pt-0.5">
        <button type="button" className="btn btn-secondary" onClick={onRunAnother}>
          Run another task
        </button>
        <button type="button" className="btn btn-primary" onClick={onClose}>
          Done
        </button>
      </div>
    </>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-[10px] border border-[#f5c2c2] bg-danger-soft px-3.5 py-[11px] text-[13px] leading-normal text-danger">
      {message}
    </div>
  );
}

function outcomeChipClass(outcome: string): string {
  if (outcome === "success") return "chip chip-green";
  if (outcome === "partial") return "chip chip-amber";
  return "chip chip-red"; // infeasible | blocked
}

function truncate(text: string, max = 90): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}
