"use client";

import { useEffect, useState } from "react";

import { formatDuration } from "@/lib/format";

/** Counts up from `startedAt` (a performance.now() timestamp) while a search runs. */
export function LiveTimer({ startedAt }: { startedAt: number }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const tick = () => setElapsed(performance.now() - startedAt);
    const interval = window.setInterval(tick, 100);
    return () => window.clearInterval(interval);
  }, [startedAt]);

  return <span className="tabular-nums">{formatDuration(elapsed)}</span>;
}
