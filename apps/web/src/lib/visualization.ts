export type ViewPoint = {
  label: string;
  value: string | null;
  source_rows: number;
};
export type ViewSpecification = {
  kind: "line" | "bar" | "table" | "kpi";
  metric: string;
  definition: string;
  unit: string;
  period_start: string;
  period_end_exclusive: string;
  reporting_timezone: string;
  filters: Record<string, string>;
  points: ViewPoint[];
  source: {
    resource_id: string;
    version_id: string;
    version_number: number;
    source_sha256: string;
    metric_definition_version: string;
  };
  insights: {
    kind: "verified_observation" | "hypothesis" | "recommendation";
    text: string;
  }[];
};
export type DashboardResponse = {
  status: "answered";
  cards: { question: string; view: ViewSpecification }[];
};

export function toFiniteNumbers(points: ViewPoint[]): (number | null)[] {
  return points.map((point) => {
    if (point.value === null) return null;
    if (!/^[+-]?\d+(?:\.\d+)?$/.test(point.value))
      throw new Error("Invalid verified value");
    const value = Number(point.value);
    if (!Number.isFinite(value))
      throw new Error("Value exceeds chart precision");
    return value;
  });
}
