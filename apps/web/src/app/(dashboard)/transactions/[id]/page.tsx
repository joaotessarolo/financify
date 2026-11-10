"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Button, Card, Field, PageHeader, Skeleton } from "@/components/ui";

type Transaction = { id: string; description: string; currency: string; amount: string; kind: string; category: string | null; accounts: Array<{ name: string }>; occurred_at: string };

export default function TransactionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [item, setItem] = useState<Transaction | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { apiFetch<Transaction>(`/api/v1/transactions/${id}/`).then(setItem); }, [id]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const updated = await apiFetch<Transaction>(`/api/v1/transactions/${id}/`, { method: "PATCH", body: JSON.stringify({ description: data.get("description"), occurred_at: new Date(`${data.get("date")}T12:00:00`).toISOString() }) });
    setItem(updated); setSaved(true);
  }

  if (!item) return <Skeleton />;
  return <main><PageHeader eyebrow="Transação" title={item.description} description={`${item.accounts.map((account) => account.name).join(" → ")} · ${item.category ?? "Sem categoria"}`} action={<Button variant="ghost" onClick={() => router.back()}>Voltar</Button>} /><Card className="detail-card"><strong className="detail-amount">{new Intl.NumberFormat("pt-BR", { style: "currency", currency: item.currency }).format(Number(item.amount))}</strong><form onSubmit={submit}><Field label="Descrição" name="description" defaultValue={item.description} required /><Field label="Data" name="date" type="date" defaultValue={item.occurred_at.slice(0, 10)} required />{saved && <p className="success">Alterações salvas.</p>}<Button>Salvar alterações</Button></form></Card></main>;
}
