"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button, Card, EmptyState, Field, PageHeader, Skeleton } from "@/components/ui";

type Category = { id: string; name: string; transaction_count: number };

export default function CategoriesPage() {
  const [items, setItems] = useState<Category[] | null>(null);
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const load = useCallback(() => apiFetch<Category[]>("/api/v1/categories/").then(setItems), []);
  useEffect(() => { load(); }, [load]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    if (editing === "new") await apiFetch("/api/v1/categories/", { method: "POST", body: JSON.stringify({ name: data.get("name") }) });
    else if (editing) await apiFetch(`/api/v1/categories/${editing.id}/`, { method: "PATCH", body: JSON.stringify({ name: data.get("name") }) });
    setEditing(null); await load();
  }
  async function archive(item: Category) { if (window.confirm(`Arquivar ${item.name}?`)) { await apiFetch(`/api/v1/categories/${item.id}/`, { method: "DELETE" }); await load(); } }

  return <main><PageHeader eyebrow="Organização" title="Categorias" description="Organize seus lançamentos do seu jeito." action={<Button onClick={() => setEditing("new")}>Nova categoria</Button>} />{editing && <Card className="editor-card"><form onSubmit={submit}><Field label="Nome" name="name" defaultValue={editing === "new" ? "" : editing.name} required /><Button>Salvar</Button></form></Card>}{!items ? <Skeleton /> : items.length === 0 ? <EmptyState title="Nenhuma categoria" description="Crie uma categoria para organizar os gastos." /> : <div className="category-grid">{items.map((item) => <Card key={item.id}><span className="category-dot" /><h2>{item.name}</h2><p>{item.transaction_count} lançamento(s)</p><div className="card-actions"><Button variant="ghost" onClick={() => setEditing(item)}>Renomear</Button><Button variant="danger" onClick={() => archive(item)}>Arquivar</Button></div></Card>)}</div>}</main>;
}
