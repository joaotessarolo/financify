"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

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

  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Financify — início">
          <span className="brand-mark">F</span>
          <span>Financify</span>
        </Link>
        <nav className="main-nav" aria-label="Navegação principal">
          {navigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link className={active ? "active" : ""} href={item.href} key={item.href}>
                <span aria-hidden="true">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span className="avatar" aria-hidden="true">JT</span>
          <span><strong>Sua conta</strong><small>Perfil e segurança</small></span>
        </div>
      </aside>
      <div className="content">{children}</div>
    </div>
  );
}
