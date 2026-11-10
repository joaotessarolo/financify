"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button, Card, EmptyState, Field, PageHeader, Skeleton } from "@/components/ui";

type Budget = { id: string; category_id: string; category: string; monthly_limit: string; spent: string };
type Category = { id: string; name: string };

export default function PlanningPage() {
  const [budgets, setBudgets] = useState<Budget[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [editing, setEditing] = useState(false);
  const load = useCallback(() => apiFetch<Budget[]>("/api/v1/budgets/").then(setBudgets), []);
  useEffect(() => { load(); apiFetch<Category[]>("/api/v1/categories/").then(setCategories); }, [load]);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); await apiFetch("/api/v1/budgets/", { method: "POST", body: JSON.stringify({ category_id: data.get("category_id"), monthly_limit: data.get("monthly_limit") }) }); setEditing(false); await load(); }
  async function remove(id: string) { await apiFetch(`/api/v1/budgets/${id}/`, { method: "DELETE" }); await load(); }

  return <main><PageHeader eyebrow="Planejamento" title="Orçamentos" description="Defina limites mensais e acompanhe o ritmo dos gastos." action={<Button onClick={() => setEditing(true)}>Novo orçamento</Button>} />{editing && <Card className="editor-card"><form onSubmit={submit}><label className="field"><span>Categoria</span><select name="category_id" required>{categories.map((category) => <option value={category.id} key={category.id}>{category.name}</option>)}</select></label><Field label="Limite mensal" name="monthly_limit" type="number" min="0.01" step="0.01" required /><Button>Salvar orçamento</Button></form></Card>}{!budgets ? <Skeleton /> : budgets.length === 0 ? <EmptyState title="Nenhum orçamento" description="Crie um limite para acompanhar uma categoria." /> : <div className="budget-grid">{budgets.map((budget) => { const percentage = Math.min(100, Number(budget.spent) / Number(budget.monthly_limit) * 100); return <Card key={budget.id}><div className="budget-head"><h2>{budget.category}</h2><Button variant="ghost" onClick={() => remove(budget.id)}>Remover</Button></div><strong>{percentage.toFixed(0)}%</strong><div className="progress"><i style={{ width: `${percentage}%` }} /></div><p>R$ {Number(budget.spent).toLocaleString("pt-BR")} de R$ {Number(budget.monthly_limit).toLocaleString("pt-BR")}</p></Card>; })}</div>}</main>;
}
