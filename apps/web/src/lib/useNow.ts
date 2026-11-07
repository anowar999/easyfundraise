"use client";

import { useEffect, useState } from "react";

/** The current time, re-rendering every `ms`, so "Scheduled 12:25" can turn into "Sending…" at 12:25 by itself. */
export function useNow(ms = 5000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}
