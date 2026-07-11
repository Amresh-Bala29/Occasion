// Shared front-end types for the Occasion web app.
export type EventStatus = "draft" | "planning" | "confirmed" | "completed";

export interface EventSummary {
  id: string;
  name: string;
  status: EventStatus;
}
