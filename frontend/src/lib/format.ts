export function formatAmount(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return "—";
  const rounded = value >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded.toLocaleString("en-US")}${unit}`;
}

export function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms.toFixed(1)} ms` : `${(ms / 1000).toFixed(1)} s`;
}
