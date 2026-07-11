"use client";

import { useState } from "react";

export function useEvent() {
  const [state, setState] = useState<unknown>(null);
  // TODO: implement useEvent
  return { state, setState } as const;
}
