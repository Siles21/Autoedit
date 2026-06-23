import React from "react";

/** Small built-in line-icon set (24x24 stroke paths) so enumerations / reveals /
 * compare-cards can be VISUAL, not just text. Reference by name in the plan
 * (e.g. enumeration item {text, icon:"bolt"}). Unknown name → a dot. */
const PATHS: Record<string, React.ReactNode> = {
  check: <path d="M4 12.5l5 5L20 6.5" />,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.5 2.2" /></>,
  bolt: <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" />,
  bank: <><path d="M3 9l9-5 9 5" /><path d="M5 9v9M9.5 9v9M14.5 9v9M19 9v9M3 21h18" /></>,
  key: <><circle cx="8" cy="14" r="4" /><path d="M11 11l9-9M17 5l2 2M14 8l2 2" /></>,
  lock: <><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 018 0v3" /></>,
  link: <><path d="M9 13a4 4 0 005.7 0l3-3A4 4 0 1012 4.3l-1.5 1.5" /><path d="M15 11a4 4 0 00-5.7 0l-3 3A4 4 0 1011.7 19.7l1.5-1.5" /></>,
  doc: <><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v4h4M9.5 12h6M9.5 16h6" /></>,
  target: <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r="0.6" fill="currentColor" /></>,
  arrow: <path d="M4 12h15M13 6l6 6-6 6" />,
  layers: <><path d="M12 3l9 5-9 5-9-5 9-5z" /><path d="M3 13l9 5 9-5M3 16.5l9 5 9-5" /></>,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></>,
  users: <><circle cx="9" cy="8" r="3.2" /><path d="M3.5 19a5.5 5.5 0 0111 0" /><path d="M16 5.5a3.2 3.2 0 010 6M21 19a5.2 5.2 0 00-4-5" /></>,
  euro: <><circle cx="12" cy="12" r="8.5" /><path d="M15.5 8.5a4.5 4.5 0 100 7M7.5 10.5h6M7.5 13.5h6" /></>,
  shield: <><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" /><path d="M9 12l2 2 4-4" /></>,
  gears: <><circle cx="12" cy="12" r="3" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /></>,
  trend: <><path d="M3 17l6-6 4 4 8-8" /><path d="M16 7h5v5" /></>,
  handshake: <path d="M3 12l4-4 3 2 3-2 4 4M7 8l2 4 3-2 3 2 2-4M9 12l1.5 1.5M12 14l1.5 1.5" />,
  building: <><rect x="5" y="3" width="14" height="18" rx="1" /><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2M10.5 21v-3h3v3" /></>,
};

export const Icon: React.FC<{ name?: string; size: number; color: string; strokeW?: number }> = ({
  name, size, color, strokeW = 2,
}) => {
  const body = (name && PATHS[name]) || <circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none" />;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"
      style={{ color, flexShrink: 0 }}>
      {body}
    </svg>
  );
};
