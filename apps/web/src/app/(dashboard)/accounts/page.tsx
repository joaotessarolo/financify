"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui";

type Account = { id: string; name: string; currency: string; balance: string; is_primary: boolean };

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  useEffect(() => { apiFetch<Account[]>("/api/v1/accounts/").then(setAccounts); }, []);
  const format = (value: string, currency: string) => new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(value));

  return <main>
    <PageHeader eyebrow="Patrimônio" title="Suas contas" description="Acompanhe onde seu dinheiro está distribuído." action={<Button>Nova conta</Button>} />
    {!accounts ? <Skeleton /> : accounts.length === 0 ? <EmptyState title="Nenhuma conta ativa" description="Crie sua primeira conta para começar." /> : <div className="account-grid">{accounts.map((account) => <Card className="account-card" key={account.id}><div><span className="account-icon">{account.name.slice(0, 1).toUpperCase()}</span>{account.is_primary && <small className="badge">Principal</small>}</div><h2>{account.name}</h2><span>Saldo atual</span><strong>{format(account.balance, account.currency)}</strong></Card>)}</div>}
  </main>;
}
