"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Button, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui";

type Summary = {
  currency: string;
  total_balance: string;
  accounts: Array<{ id: string; name: string; balance: string }>;
  month: { income: string; expenses: string; net: string };
  recent_transactions: Array<{ id: string; description: string; amount: string; category: string | null; occurred_at: string }>;
  budgets: Array<{ category: string; limit: string; spent: string }>;
  upcoming_recurrences: Array<{ id: string; description: string; amount: string; next_run_on: string }>;
};

const money = (value: string, currency: string) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(value));

export default function Dashboard() {
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Summary>("/api/v1/dashboard/summary/")
      .then(setSummary)
      .catch(() => {
        setError("Não foi possível carregar seu resumo.");
        router.replace("/login");
      });
  }, [router]);

  if (!summary) return <main>{error ? <EmptyState title="Resumo indisponível" description={error} /> : <Skeleton lines={5} />}</main>;

  return (
    <main>
      <PageHeader eyebrow="Visão geral" title="Seu mês financeiro" action={<Button variant="secondary">Novo lançamento</Button>} />
      <div className="hero-card"><span>Saldo total</span><strong>{money(summary.total_balance, summary.currency)}</strong><small>{summary.accounts.length} conta(s) ativa(s)</small></div>
      <div className="stat-grid">
        <Card><span>Receitas</span><strong className="positive">{money(summary.month.income, summary.currency)}</strong></Card>
        <Card><span>Despesas</span><strong className="negative">{money(summary.month.expenses, summary.currency)}</strong></Card>
        <Card><span>Resultado</span><strong>{money(summary.month.net, summary.currency)}</strong></Card>
      </div>
      <div className="panel-grid">
        <Card className="panel"><h2>Contas</h2>{summary.accounts.map((account) => <div className="row" key={account.id}><span>{account.name}</span><strong>{money(account.balance, summary.currency)}</strong></div>)}</Card>
        <Card className="panel"><h2>Últimos lançamentos</h2>{summary.recent_transactions.length ? summary.recent_transactions.map((item) => <div className="row" key={item.id}><span>{item.description}<small>{item.category ?? "Sem categoria"}</small></span><strong>{money(item.amount, summary.currency)}</strong></div>) : <EmptyState title="Tudo limpo por aqui" description="Seus lançamentos confirmados aparecerão nesta lista." />}</Card>
      </div>
    </main>
  );
}
