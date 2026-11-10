"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Card, EmptyState, PageHeader, Skeleton } from "@/components/ui";

type Transaction = { id: string; description: string; currency: string; amount: string; kind: "EXPENSE" | "INCOME" | "TRANSFER"; category: string | null; accounts: Array<{ name: string }>; occurred_at: string };

export default function TransactionsPage() {
  const [items, setItems] = useState<Transaction[] | null>(null);
  useEffect(() => { apiFetch<Transaction[]>("/api/v1/transactions/").then(setItems); }, []);
  const money = (item: Transaction) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: item.currency }).format(Number(item.amount));

  return <main>
    <PageHeader eyebrow="Movimentações" title="Transações" description="Tudo que entrou, saiu ou mudou de conta." />
    {!items ? <Skeleton lines={5} /> : items.length === 0 ? <EmptyState title="Nenhuma transação" description="Confirme um lançamento no Telegram para vê-lo aqui." /> : <Card className="transaction-list">{items.map((item) => <div className="transaction-row" key={item.id}><span className={`transaction-kind kind-${item.kind.toLowerCase()}`}>{item.kind === "EXPENSE" ? "↓" : item.kind === "INCOME" ? "↑" : "↔"}</span><span><strong>{item.description}</strong><small>{item.category ?? "Transferência"} · {new Date(item.occurred_at).toLocaleDateString("pt-BR")}</small></span><span className="transaction-account">{item.accounts.map((account) => account.name).join(" → ")}</span><strong className={item.kind === "EXPENSE" ? "negative" : item.kind === "INCOME" ? "positive" : ""}>{item.kind === "EXPENSE" ? "−" : item.kind === "INCOME" ? "+" : ""}{money(item)}</strong></div>)}</Card>}
  </main>;
}
