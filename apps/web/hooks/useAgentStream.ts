"use client";

import { useState } from "react";

export function useAgentStream() {
  const [state, setState] = useState<unknown>(null);
  // TODO: implement useAgentStream
  return { state, setState } as const;
}
