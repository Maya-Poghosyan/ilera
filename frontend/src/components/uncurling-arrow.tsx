export function UncurlingArrow() {
  return (
    <svg
      viewBox="0 0 14 12"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-3 w-[14px] overflow-visible"
    >
      {/* Drawn left to right: dashoffset trims the far end, so it extends rightwards. */}
      <path
        d="M1 6H21"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={0.4}
        className="transition-[stroke-dashoffset] duration-300 ease-out group-hover/button:[stroke-dashoffset:0]"
      />
      <path
        d="M9 2l4 4-4 4"
        className="transition-transform duration-300 ease-out group-hover/button:translate-x-[8px]"
      />
    </svg>
  );
}
