import { describe, expect, it } from "vitest";
import { formatDate, formatMoney } from "./format";

describe("format helpers", () => {
  it("formats Brazilian currency", () => {
    expect(formatMoney("1250.50", "BRL")).toContain("1.250,50");
  });

  it("formats a local date without a timezone shift", () => {
    expect(formatDate(new Date(2026, 10, 18, 12))).toBe("18/11/2026");
  });
});
