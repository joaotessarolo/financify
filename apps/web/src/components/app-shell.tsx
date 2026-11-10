"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useSession } from "@/components/session-provider";
import { Button } from "@/components/ui";

const navigation = [
  { href: "/", label: "Visão geral", icon: "⌂" },
  { href: "/transactions", label: "Transações", icon: "↕" },
  { href: "/accounts", label: "Contas", icon: "◫" },
  { href: "/categories", label: "Categorias", icon: "◇" },
  { href: "/planning", label: "Planejamento", icon: "◎" },
  { href: "/settings", label: "Configurações", icon: "⚙" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user, loading, logout } = useSession();
  const name = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.email || "Sua conta";
  const initials = user?.first_name || user?.email ? (user.first_name || user.email).slice(0, 2).toUpperCase() : "…";

  return (
    <div className="dashboard-shell">
      <a className="skip-link" href="#main-content">Pular para o conteúdo</a>
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Financify — início">
          <span className="brand-mark">F</span>
          <span>Financify</span>
        </Link>
        <nav className="main-nav" aria-label="Navegação principal">
          {navigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link className={active ? "active" : ""} href={item.href} key={item.href} aria-current={active ? "page" : undefined}>
                <span aria-hidden="true">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span className="avatar" aria-hidden="true">{initials}</span>
          <span><strong>{loading ? "Carregando…" : name}</strong><small>{user?.email ?? "Perfil e segurança"}</small></span>
          <Button className="logout-button" variant="ghost" onClick={logout} aria-label="Sair">↪</Button>
        </div>
      </aside>
      <div className="content" id="main-content" tabIndex={-1}>{children}</div>
    </div>
  );
}
