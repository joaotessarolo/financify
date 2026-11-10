import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState, Field, PageHeader, Skeleton } from "./ui";

describe("shared interface components", () => {
  it("connects a field label to its input", () => {
    render(<Field label="Nome da conta" name="name" />);
    expect(screen.getByRole("textbox", { name: "Nome da conta" })).toBeInTheDocument();
  });

  it("renders headings and loading feedback with accessible names", () => {
    const { rerender } = render(<PageHeader eyebrow="Resumo" title="Seu mês" />);
    expect(screen.getByRole("heading", { level: 1, name: "Seu mês" })).toBeInTheDocument();
    rerender(<Skeleton />);
    expect(screen.getByLabelText("Carregando")).toBeInTheDocument();
  });

  it("announces an empty state without exposing its decoration", () => {
    render(<EmptyState title="Sem lançamentos" description="Registre o primeiro." />);
    expect(screen.getByText("Sem lançamentos")).toBeInTheDocument();
    expect(screen.getByText("Registre o primeiro.")).toBeInTheDocument();
  });
});
