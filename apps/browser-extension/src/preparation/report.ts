export type PreparationProgressReportType = "progress" | "ready_for_review";

export function preparationProgressResult(
  type: PreparationProgressReportType,
  completed: number,
  total: number,
): { status: PreparationProgressReportType; completed: number; total: number } {
  const safeTotal = Math.max(0, Math.trunc(total));
  return {
    status: type,
    completed: Math.min(safeTotal, Math.max(0, Math.trunc(completed))),
    total: safeTotal,
  };
}
