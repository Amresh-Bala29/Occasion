"use client";

import { useState } from "react";

export function useVoice() {
  const [state, setState] = useState<unknown>(null);
  // TODO: implement useVoice
  return { state, setState } as const;
}
