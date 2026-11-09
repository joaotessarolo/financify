"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

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

  if (!summary) return <main className="loading">{error || "Organizando seus números…"}</main>;

  return (
    <main className="dashboard-shell">
      <aside><strong>Financify</strong><nav><a className="active">Visão geral</a><a>Transações</a><a>Contas</a><a>Planejamento</a></nav></aside>
      <section className="content">
        <header><div><span className="eyebrow">Visão geral</span><h1>Seu mês financeiro</h1></div><button className="secondary">Novo lançamento</button></header>
        <div className="hero-card"><span>Saldo total</span><strong>{money(summary.total_balance, summary.currency)}</strong><small>{summary.accounts.length} conta(s) ativa(s)</small></div>
        <div className="stat-grid">
          <article><span>Receitas</span><strong className="positive">{money(summary.month.income, summary.currency)}</strong></article>
          <article><span>Despesas</span><strong className="negative">{money(summary.month.expenses, summary.currency)}</strong></article>
          <article><span>Resultado</span><strong>{money(summary.month.net, summary.currency)}</strong></article>
        </div>
        <div className="panel-grid">
          <article className="panel"><h2>Contas</h2>{summary.accounts.map((account) => <div className="row" key={account.id}><span>{account.name}</span><strong>{money(account.balance, summary.currency)}</strong></div>)}</article>
          <article className="panel"><h2>Últimos lançamentos</h2>{summary.recent_transactions.length ? summary.recent_transactions.map((item) => <div className="row" key={item.id}><span>{item.description}<small>{item.category ?? "Sem categoria"}</small></span><strong>{money(item.amount, summary.currency)}</strong></div>) : <p className="empty">Nenhum lançamento confirmado ainda.</p>}</article>
        </div>
      </section>
    </main>
  );
}
