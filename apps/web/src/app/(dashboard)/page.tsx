"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { getBudgetProgress, getBudgetStatus } from "@/lib/budgets";
import { Button, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui";

type Summary = {
  currency: string;
  total_balance: string;
  accounts: Array<{ id: string; name: string; balance: string }>;
  month: { income: string; expenses: string; net: string };
  spending_by_category: Array<{ category: string; amount: string }>;
  recent_transactions: Array<{
    id: string;
    description: string;
    amount: string;
    category: string | null;
    occurred_at: string;
  }>;
  budgets: Array<{ category: string; limit: string; spent: string }>;
  upcoming_recurrences: Array<{
    id: string;
    description: string;
    amount: string;
    next_run_on: string;
  }>;
};

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

  if (!summary)
    return (
      <main>
        {error ? (
          <EmptyState title="Resumo indisponível" description={error} />
        ) : (
          <Skeleton lines={5} />
        )}
      </main>
    );

  const largestCategory = Math.max(
    ...summary.spending_by_category.map((item) => Number(item.amount)),
    1,
  );

  return (
    <main>
      <PageHeader
        eyebrow="Visão geral"
        title="Seu mês financeiro"
        action={<Button variant="secondary">Novo lançamento</Button>}
      />
      <div className="hero-card">
        <span>Saldo total</span>
        <strong>{formatMoney(summary.total_balance, summary.currency)}</strong>
        <small>{summary.accounts.length} conta(s) ativa(s)</small>
      </div>
      <div className="stat-grid">
        <Card>
          <span>Receitas</span>
          <strong className="positive">
            {formatMoney(summary.month.income, summary.currency)}
          </strong>
        </Card>
        <Card>
          <span>Despesas</span>
          <strong className="negative">
            {formatMoney(summary.month.expenses, summary.currency)}
          </strong>
        </Card>
        <Card>
          <span>Resultado</span>
          <strong>{formatMoney(summary.month.net, summary.currency)}</strong>
        </Card>
      </div>
      <div className="panel-grid">
        <Card className="panel">
          <h2>Contas</h2>
          {summary.accounts.map((account) => (
            <div className="row" key={account.id}>
              <span>{account.name}</span>
              <strong>{formatMoney(account.balance, summary.currency)}</strong>
            </div>
          ))}
        </Card>
        <Card className="panel">
          <h2>Últimos lançamentos</h2>
          {summary.recent_transactions.length ? (
            summary.recent_transactions.map((item) => (
              <div className="row" key={item.id}>
                <span>
                  {item.description}
                  <small>{item.category ?? "Sem categoria"}</small>
                </span>
                <strong>{formatMoney(item.amount, summary.currency)}</strong>
              </div>
            ))
          ) : (
            <EmptyState
              title="Tudo limpo por aqui"
              description="Seus lançamentos confirmados aparecerão nesta lista."
            />
          )}
        </Card>
      </div>
      <div className="insight-grid">
        <Card className="panel">
          <h2>Gastos por categoria</h2>
          {summary.spending_by_category.length ? (
            <div className="bar-chart">
              {summary.spending_by_category.map((item) => (
                <div className="bar-row" key={item.category}>
                  <span>{item.category}</span>
                  <div>
                    <i style={{ width: `${(Number(item.amount) / largestCategory) * 100}%` }} />
                  </div>
                  <strong>{formatMoney(item.amount, summary.currency)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Sem gastos neste mês"
              description="As categorias aparecem aqui conforme você registra despesas."
            />
          )}
        </Card>
        <Card className="panel">
          <h2>Orçamentos do mês</h2>
          {summary.budgets.length ? (
            summary.budgets.map((budget) => {
              const progress = getBudgetProgress(budget.spent, budget.limit);
              const status = getBudgetStatus(progress);
              return (
                <div className={`budget-summary budget-${status}`} key={budget.category}>
                  <div>
                    <span>{budget.category}</span>
                    <strong>
                      {formatMoney(budget.spent, summary.currency)} de{" "}
                      {formatMoney(budget.limit, summary.currency)}
                    </strong>
                  </div>
                  <div
                    className="progress"
                    aria-label={`${budget.category}: ${Math.round(progress)}% utilizado`}
                  >
                    <i style={{ width: `${Math.min(progress, 100)}%` }} />
                  </div>
                  {status !== "safe" && (
                    <small className="budget-message">
                      {status === "exceeded"
                        ? "Limite ultrapassado"
                        : "Você já usou mais de 80% deste orçamento"}
                    </small>
                  )}
                </div>
              );
            })
          ) : (
            <EmptyState
              title="Nenhum orçamento definido"
              description="Crie limites mensais no planejamento para acompanhar seu ritmo."
            />
          )}
        </Card>
      </div>
      <Card className="panel upcoming-panel">
        <div className="panel-heading">
          <h2>Próximos lançamentos recorrentes</h2>
          <Link href="/planning">Ver planejamento</Link>
        </div>
        {summary.upcoming_recurrences.length ? (
          <div className="upcoming-grid">
            {summary.upcoming_recurrences.map((item) => (
              <div className="upcoming-item" key={item.id}>
                <span>
                  {item.description}
                  <small>{formatDate(`${item.next_run_on}T12:00:00`)}</small>
                </span>
                <strong>{formatMoney(item.amount, summary.currency)}</strong>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Nenhuma recorrência próxima"
            description="Crie despesas ou receitas recorrentes no planejamento."
          />
        )}
      </Card>
    </main>
  );
}
