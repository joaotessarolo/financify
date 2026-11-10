"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button, Card, PageHeader, Skeleton } from "@/components/ui";
import { useSession } from "@/components/session-provider";

type TelegramStatus = { connected: boolean; linked_at: string | null };
type TelegramLink = { url: string; expires_at: string };

export default function SettingsPage() {
  const { user } = useSession();
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null);
  const [link, setLink] = useState<TelegramLink | null>(null);
  const load = useCallback(() => apiFetch<TelegramStatus>("/api/v1/telegram/link/").then(setTelegram), []);
  useEffect(() => { load(); }, [load]);
  async function connect() { setLink(await apiFetch<TelegramLink>("/api/v1/telegram/link/", { method: "POST" })); }
  async function disconnect() { if (!window.confirm("Desconectar o Telegram?")) return; await apiFetch("/api/v1/telegram/link/", { method: "DELETE" }); setLink(null); await load(); }

  return <main><PageHeader eyebrow="Preferências" title="Configurações" description="Gerencie perfil, segurança e integrações." /><div className="settings-grid"><Card><h2>Seu perfil</h2><div className="definition-list"><span>E-mail<strong>{user?.email ?? "—"}</strong></span><span>Moeda<strong>{user?.currency ?? "—"}</strong></span><span>Fuso horário<strong>{user?.timezone ?? "—"}</strong></span></div></Card><Card><div className="integration-head"><span className="telegram-mark">✈</span><div><h2>Telegram</h2><p>Registre lançamentos por texto ou áudio.</p></div></div>{!telegram ? <Skeleton lines={1} /> : telegram.connected ? <><p className="status-connected">● Conectado desde {new Date(telegram.linked_at!).toLocaleDateString("pt-BR")}</p><Button variant="danger" onClick={disconnect}>Desconectar</Button></> : <><p className="empty">Nenhum Telegram conectado.</p><Button onClick={connect}>Gerar link de conexão</Button></>}{link && <div className="link-box"><p>Este link expira em alguns minutos.</p><a href={link.url} target="_blank" rel="noreferrer">Abrir bot no Telegram</a></div>}</Card></div></main>;
}
