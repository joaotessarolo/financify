export type BudgetStatus = "safe" | "warning" | "exceeded";

export function getBudgetProgress(spent: string | number, limit: string | number) {
  const percentage = (Number(spent) / Number(limit)) * 100;
  return Number.isFinite(percentage) ? Math.max(percentage, 0) : 0;
}

export function getBudgetStatus(progress: number): BudgetStatus {
  if (progress >= 100) return "exceeded";
  if (progress >= 80) return "warning";
  return "safe";
}
