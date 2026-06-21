"use client";

import Link from "next/link";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { ToastProvider } from "@/components/toast";
import { UserMenu } from "@/components/user-menu";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/benchmark", label: "Benchmark" },
  { href: "/about", label: "About" },
] as const;

function Header() {
  const { user } = useAuth();
  return (
    <header className="border-b border-border">
      <nav className="mx-auto max-w-6xl flex items-center gap-6 px-4 py-3">
        <Link
          href="/"
          className="font-semibold text-lg tracking-tight shrink-0 hover:opacity-80 transition-opacity"
        >
          Foreman
        </Link>

        <div className="flex gap-4 text-sm text-muted-foreground flex-1">
          {NAV_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="hover:text-foreground transition-colors"
            >
              {label}
            </Link>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <a
            href="https://github.com/suyashisingh/Foreman"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            GitHub
          </a>
          {user ? (
            <UserMenu />
          ) : (
            <Link
              href="/login"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Sign in
            </Link>
          )}
        </div>
      </nav>
    </header>
  );
}

// AppShell wraps the entire application with shared providers and the nav bar.
// It is a client component so that Header and UserMenu can read auth state.
// Server component children (page content) are passed through as opaque RSC trees.
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>
        <Header />
        <main className="flex-1">{children}</main>
      </ToastProvider>
    </AuthProvider>
  );
}
