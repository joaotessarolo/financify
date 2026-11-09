"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await apiFetch<void>("/api/v1/auth/login/", {
        method: "POST",
        body: JSON.stringify({ email: data.get("email"), password: data.get("password") }),
      });
      router.replace("/");
    } catch {
      setError("Não foi possível entrar. Confira seu e-mail e sua senha.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <span className="eyebrow">Financify</span>
        <h1>Seu dinheiro, sem ruído.</h1>
        <p>Entre para acompanhar contas, gastos e metas em um só lugar.</p>
        <form onSubmit={submit}>
          <label>E-mail<input name="email" type="email" autoComplete="email" required /></label>
          <label>Senha<input name="password" type="password" autoComplete="current-password" required /></label>
          {error && <div className="error" role="alert">{error}</div>}
          <button disabled={loading}>{loading ? "Entrando…" : "Entrar"}</button>
        </form>
      </section>
    </main>
  );
}
