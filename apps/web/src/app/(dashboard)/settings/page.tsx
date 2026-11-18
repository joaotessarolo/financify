"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Alert, Button, Card, Field, PageHeader, Skeleton } from "@/components/ui";
import { useSession } from "@/components/session-provider";

type TelegramStatus = { connected: boolean; linked_at: string | null };
type TelegramLink = { url: string; expires_at: string };

export default function SettingsPage() {
  const { user, refresh } = useSession();
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null);
  const [link, setLink] = useState<TelegramLink | null>(null);
  const [profileSaved, setProfileSaved] = useState(false);
  const load = useCallback(
    () => apiFetch<TelegramStatus>("/api/v1/telegram/link/").then(setTelegram),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);
  async function connect() {
    setLink(await apiFetch<TelegramLink>("/api/v1/telegram/link/", { method: "POST" }));
  }
  async function disconnect() {
    if (!window.confirm("Desconectar o Telegram?")) return;
    await apiFetch("/api/v1/telegram/link/", { method: "DELETE" });
    setLink(null);
    await load();
  }
  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await apiFetch("/api/v1/users/me/", {
      method: "PATCH",
      body: JSON.stringify({
        first_name: data.get("first_name"),
        last_name: data.get("last_name"),
        currency: data.get("currency"),
        timezone: data.get("timezone"),
      }),
    });
    await refresh();
    setProfileSaved(true);
  }

  return (
    <main>
      <PageHeader
        eyebrow="Preferências"
        title="Configurações"
        description="Gerencie perfil, segurança e integrações."
      />
      <div className="settings-grid">
        <Card>
          <h2>Seu perfil</h2>
          <p className="empty">{user?.email ?? "—"}</p>
          {user && (
            <form className="settings-form" onSubmit={saveProfile}>
              <div className="name-fields">
                <Field label="Nome" name="first_name" defaultValue={user.first_name} />
                <Field label="Sobrenome" name="last_name" defaultValue={user.last_name} />
              </div>
              <label className="field">
                <span>Moeda</span>
                <select name="currency" defaultValue={user.currency}>
                  <option value="BRL">BRL — Real</option>
                  <option value="USD">USD — Dólar</option>
                  <option value="EUR">EUR — Euro</option>
                </select>
              </label>
              <label className="field">
                <span>Fuso horário</span>
                <select name="timezone" defaultValue={user.timezone}>
                  <option value="America/Sao_Paulo">São Paulo</option>
                  <option value="UTC">UTC</option>
                  <option value="America/New_York">Nova York</option>
                  <option value="Europe/Lisbon">Lisboa</option>
                </select>
              </label>
              {profileSaved && <Alert tone="success">Perfil atualizado.</Alert>}
              <Button>Salvar perfil</Button>
            </form>
          )}
        </Card>
        <Card>
          <div className="integration-head">
            <span className="telegram-mark">✈</span>
            <div>
              <h2>Telegram</h2>
              <p>Registre lançamentos por texto ou áudio.</p>
            </div>
          </div>
          {!telegram ? (
            <Skeleton lines={1} />
          ) : telegram.connected ? (
            <>
              <p className="status-connected">
                ● Conectado desde {formatDate(telegram.linked_at!)}
              </p>
              <Button variant="danger" onClick={disconnect}>
                Desconectar
              </Button>
            </>
          ) : (
            <>
              <p className="empty">Nenhum Telegram conectado.</p>
              <Button onClick={connect}>Gerar link de conexão</Button>
            </>
          )}
          {link && (
            <div className="link-box">
              <p>Este link expira em alguns minutos.</p>
              <a href={link.url} target="_blank" rel="noreferrer">
                Abrir bot no Telegram
              </a>
            </div>
          )}
        </Card>
      </div>
    </main>
  );
}
