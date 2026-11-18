import { describe, expect, it } from "vitest";
import { getBudgetProgress, getBudgetStatus } from "./budgets";

describe("budget status", () => {
  it("warns at 80 percent and marks exceeded limits", () => {
    expect(getBudgetStatus(79)).toBe("safe");
    expect(getBudgetStatus(80)).toBe("warning");
    expect(getBudgetStatus(100)).toBe("exceeded");
  });

  it("calculates progress safely", () => {
    expect(getBudgetProgress("400", "500")).toBe(80);
    expect(getBudgetProgress("10", "0")).toBe(0);
  });
});
