"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button, Card, EmptyState, Field, PageHeader, Skeleton } from "@/components/ui";

type Account = { id: string; name: string; currency: string; balance: string; is_primary: boolean };

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [editing, setEditing] = useState<Account | "new" | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => apiFetch<Account[]>("/api/v1/accounts/").then(setAccounts), []);
  useEffect(() => { load(); }, [load]);
  const format = (value: string, currency: string) => new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(value));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const data = new FormData(event.currentTarget);
    try {
      if (editing === "new") await apiFetch("/api/v1/accounts/", { method: "POST", body: JSON.stringify({ name: data.get("name"), opening_balance: data.get("opening_balance") }) });
      else if (editing) await apiFetch(`/api/v1/accounts/${editing.id}/`, { method: "PATCH", body: JSON.stringify({ name: data.get("name") }) });
      setEditing(null); await load();
    } catch { setError("Não foi possível salvar a conta. Confira o nome e o saldo."); }
  }

  async function archive(account: Account) {
    if (!window.confirm(`Arquivar a conta ${account.name}?`)) return;
    await apiFetch(`/api/v1/accounts/${account.id}/`, { method: "DELETE" });
    await load();
  }

  return <main>
    <PageHeader eyebrow="Patrimônio" title="Suas contas" description="Acompanhe onde seu dinheiro está distribuído." action={<Button onClick={() => setEditing("new")}>Nova conta</Button>} />
    {editing && <Card className="editor-card"><form onSubmit={submit}><div><h2>{editing === "new" ? "Nova conta" : "Renomear conta"}</h2><Button type="button" variant="ghost" onClick={() => setEditing(null)}>Fechar</Button></div><Field label="Nome" name="name" defaultValue={editing === "new" ? "" : editing.name} required />{editing === "new" && <Field label="Saldo atual" name="opening_balance" type="number" step="0.01" defaultValue="0.00" required />}{error && <div className="error" role="alert">{error}</div>}<Button>Salvar conta</Button></form></Card>}
    {!accounts ? <Skeleton /> : accounts.length === 0 ? <EmptyState title="Nenhuma conta ativa" description="Crie sua primeira conta para começar." /> : <div className="account-grid">{accounts.map((account) => <Card className="account-card" key={account.id}><div><span className="account-icon">{account.name.slice(0, 1).toUpperCase()}</span>{account.is_primary && <small className="badge">Principal</small>}</div><h2>{account.name}</h2><span>Saldo atual</span><strong>{format(account.balance, account.currency)}</strong><div className="card-actions"><Button variant="ghost" onClick={() => setEditing(account)}>Renomear</Button>{!account.is_primary && <Button variant="danger" onClick={() => archive(account)}>Arquivar</Button>}</div></Card>)}</div>}
  </main>;
}
