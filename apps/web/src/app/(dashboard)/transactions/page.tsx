"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button, Card, EmptyState, Field, PageHeader, Skeleton } from "@/components/ui";

type Transaction = { id: string; description: string; currency: string; amount: string; kind: "EXPENSE" | "INCOME" | "TRANSFER"; category: string | null; accounts: Array<{ name: string }>; occurred_at: string };
type Account = { id: string; name: string };

export default function TransactionsPage() {
  const [items, setItems] = useState<Transaction[] | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  useEffect(() => { apiFetch<Transaction[]>("/api/v1/transactions/").then(setItems); apiFetch<Account[]>("/api/v1/accounts/").then(setAccounts); }, []);
  const money = (item: Transaction) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: item.currency }).format(Number(item.amount));

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const query = new URLSearchParams();
    for (const key of ["q", "kind", "account", "from", "to"]) {
      const value = data.get(key)?.toString(); if (value) query.set(key, value);
    }
    setItems(null);
    apiFetch<Transaction[]>(`/api/v1/transactions/?${query}`).then(setItems);
  }

  return <main>
    <PageHeader eyebrow="Movimentações" title="Transações" description="Tudo que entrou, saiu ou mudou de conta." />
    <Card className="filters"><form onSubmit={filter}><Field label="Buscar" name="q" placeholder="Mercado, salário…" /><label className="field"><span>Tipo</span><select name="kind"><option value="">Todos</option><option value="EXPENSE">Despesas</option><option value="INCOME">Receitas</option><option value="TRANSFER">Transferências</option></select></label><label className="field"><span>Conta</span><select name="account"><option value="">Todas</option>{accounts.map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label><Field label="De" name="from" type="date" /><Field label="Até" name="to" type="date" /><Button>Filtrar</Button></form></Card>
    {!items ? <Skeleton lines={5} /> : items.length === 0 ? <EmptyState title="Nenhuma transação" description="Confirme um lançamento no Telegram para vê-lo aqui." /> : <Card className="transaction-list">{items.map((item) => <div className="transaction-row" key={item.id}><span className={`transaction-kind kind-${item.kind.toLowerCase()}`}>{item.kind === "EXPENSE" ? "↓" : item.kind === "INCOME" ? "↑" : "↔"}</span><span><strong>{item.description}</strong><small>{item.category ?? "Transferência"} · {new Date(item.occurred_at).toLocaleDateString("pt-BR")}</small></span><span className="transaction-account">{item.accounts.map((account) => account.name).join(" → ")}</span><strong className={item.kind === "EXPENSE" ? "negative" : item.kind === "INCOME" ? "positive" : ""}>{item.kind === "EXPENSE" ? "−" : item.kind === "INCOME" ? "+" : ""}{money(item)}</strong></div>)}</Card>}
  </main>;
}
