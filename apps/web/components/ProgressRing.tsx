interface ProgressRingProps {
  percent: number;
  size?: number;
}

/** Circular completion gauge with the percentage in the center. */
export function ProgressRing({ percent, size = 116 }: ProgressRingProps) {
  const strokeWidth = 9;
  const radius = (100 - strokeWidth) / 2; // fits a 100x100 viewBox
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(100, Math.max(0, Math.round(percent)));
  const offset = circumference * (1 - clamped / 100);

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${clamped}% complete`}
    >
      <svg viewBox="0 0 100 100" className="size-full -rotate-90">
        <circle className="fill-none stroke-[#e7ebf4]" cx="50" cy="50" r={radius} strokeWidth={strokeWidth} />
        <circle
          className="fill-none stroke-brand"
          cx="50"
          cy="50"
          r={radius}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center" aria-hidden="true">
        <span className="text-[26px] leading-none font-bold tracking-[-0.02em]">
          {clamped}
          <span className="text-[14px] font-semibold text-ink-soft">%</span>
        </span>
        <span className="mt-[3px] text-[11px] text-ink-soft">complete</span>
      </div>
    </div>
  );
}
