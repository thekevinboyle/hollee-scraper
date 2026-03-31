/** 10 supported states with metadata */
export const STATES = [
  { code: "TX", name: "Texas", tier: 1 },
  { code: "NM", name: "New Mexico", tier: 1 },
  { code: "ND", name: "North Dakota", tier: 1 },
  { code: "OK", name: "Oklahoma", tier: 1 },
  { code: "CO", name: "Colorado", tier: 1 },
  { code: "WY", name: "Wyoming", tier: 2 },
  { code: "LA", name: "Louisiana", tier: 2 },
  { code: "PA", name: "Pennsylvania", tier: 2 },
  { code: "CA", name: "California", tier: 2 },
  { code: "AK", name: "Alaska", tier: 2 },
] as const;

export const STATE_CODES = STATES.map((s) => s.code);

export const WELL_STATUSES = [
  "active",
  "inactive",
  "plugged",
  "permitted",
  "drilling",
  "completed",
  "shut_in",
  "temporarily_abandoned",
  "unknown",
] as const;

export const DOC_TYPES = [
  "well_permit",
  "completion_report",
  "production_report",
  "spacing_order",
  "plugging_report",
  "inspection_record",
  "incident_report",
] as const;

export const CONFIDENCE_THRESHOLDS = {
  HIGH: 0.85,
  MEDIUM: 0.5,
} as const;

export const CONFIDENCE_RANGES = [
  { label: "All", min: undefined, max: undefined },
  { label: "High (\u226585%)", min: 0.85, max: undefined },
  { label: "Medium (50-84%)", min: 0.5, max: 0.84 },
  { label: "Low (<50%)", min: undefined, max: 0.49 },
] as const;

/** Map pin colors by well status */
export const STATUS_COLORS: Record<string, string> = {
  active: "#22c55e",
  drilling: "#3b82f6",
  completed: "#06b6d4",
  plugged: "#ef4444",
  inactive: "#f59e0b",
  shut_in: "#8b5cf6",
  permitted: "#a855f7",
  unknown: "#9ca3af",
};
