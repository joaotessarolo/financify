"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button, Card, EmptyState, Field, PageHeader, Skeleton } from "@/components/ui";

type Budget = { id: string; category_id: string; category: string; monthly_limit: string; spent: string };
type Category = { id: string; name: string };
type Recurrence = { id: string; kind: "EXPENSE" | "INCOME"; amount: string; description: string; day_of_month: number; next_run_on: string; is_active: boolean };

export default function PlanningPage() {
  const [budgets, setBudgets] = useState<Budget[] | null>(null);
  const [recurrences, setRecurrences] = useState<Recurrence[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [editor, setEditor] = useState<"budget" | "recurrence" | null>(null);
  const load = useCallback(async () => { const [a, b] = await Promise.all([apiFetch<Budget[]>("/api/v1/budgets/"), apiFetch<Recurrence[]>("/api/v1/recurrences/")]); setBudgets(a); setRecurrences(b); }, []);
  useEffect(() => { load(); apiFetch<Category[]>("/api/v1/categories/").then(setCategories); }, [load]);
  async function saveBudget(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); await apiFetch("/api/v1/budgets/", { method: "POST", body: JSON.stringify({ category_id: data.get("category_id"), monthly_limit: data.get("monthly_limit") }) }); setEditor(null); await load(); }
  async function saveRecurrence(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); await apiFetch("/api/v1/recurrences/", { method: "POST", body: JSON.stringify({ kind: data.get("kind"), amount: data.get("amount"), description: data.get("description"), day_of_month: data.get("day") }) }); setEditor(null); await load(); }
  async function removeBudget(id: string) { await apiFetch(`/api/v1/budgets/${id}/`, { method: "DELETE" }); await load(); }
  async function toggle(item: Recurrence) { await apiFetch(`/api/v1/recurrences/${item.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !item.is_active }) }); await load(); }
  async function removeRecurrence(id: string) { await apiFetch(`/api/v1/recurrences/${id}/`, { method: "DELETE" }); await load(); }

  return <main>
    <PageHeader eyebrow="Planejamento" title="Orçamentos e recorrências" description="Defina limites e organize o que se repete todo mês." action={<div className="header-actions"><Button variant="secondary" onClick={() => setEditor("recurrence")}>Nova recorrência</Button><Button onClick={() => setEditor("budget")}>Novo orçamento</Button></div>} />
    {editor === "budget" && <Card className="editor-card"><form onSubmit={saveBudget}><label className="field"><span>Categoria</span><select name="category_id" required>{categories.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><Field label="Limite mensal" name="monthly_limit" type="number" min="0.01" step="0.01" required /><Button>Salvar orçamento</Button></form></Card>}
    {editor === "recurrence" && <Card className="editor-card"><form onSubmit={saveRecurrence}><label className="field"><span>Tipo</span><select name="kind"><option value="EXPENSE">Despesa</option><option value="INCOME">Receita</option></select></label><Field label="Descrição" name="description" required /><Field label="Valor" name="amount" type="number" min="0.01" step="0.01" required /><Field label="Dia do mês" name="day" type="number" min="1" max="28" required /><Button>Salvar recorrência</Button></form></Card>}
    <section className="planning-section"><h2>Orçamentos</h2>{!budgets ? <Skeleton /> : budgets.length === 0 ? <EmptyState title="Nenhum orçamento" description="Crie um limite para acompanhar uma categoria." /> : <div className="budget-grid">{budgets.map((budget) => { const percentage = Math.min(100, Number(budget.spent) / Number(budget.monthly_limit) * 100); return <Card key={budget.id}><div className="budget-head"><h2>{budget.category}</h2><Button variant="ghost" onClick={() => removeBudget(budget.id)}>Remover</Button></div><strong>{percentage.toFixed(0)}%</strong><div className="progress"><i style={{ width: `${percentage}%` }} /></div><p>R$ {Number(budget.spent).toLocaleString("pt-BR")} de R$ {Number(budget.monthly_limit).toLocaleString("pt-BR")}</p></Card>; })}</div>}</section>
    <section className="planning-section"><h2>Recorrências</h2>{!recurrences ? <Skeleton /> : recurrences.length === 0 ? <EmptyState title="Nenhuma recorrência" description="Cadastre contas fixas ou receitas mensais." /> : <Card className="recurrence-list">{recurrences.map((item) => <div className="row" key={item.id}><span><strong>{item.description}</strong><small>Todo dia {item.day_of_month} · próxima em {new Date(`${item.next_run_on}T12:00:00`).toLocaleDateString("pt-BR")}</small></span><strong>R$ {Number(item.amount).toLocaleString("pt-BR")}</strong><div className="card-actions"><Button variant="ghost" onClick={() => toggle(item)}>{item.is_active ? "Pausar" : "Retomar"}</Button><Button variant="danger" onClick={() => removeRecurrence(item.id)}>Remover</Button></div></div>)}</Card>}</section>
  </main>;
}
