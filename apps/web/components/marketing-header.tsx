"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { UserMenu } from "@/components/user-menu";

// #28363C — dark slate-teal, the primary brand dark used throughout marketing.
const HEADER_BG = "#28363C";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About" },
  { href: "/benchmark", label: "Benchmark" },
] as const;

export function MarketingHeader() {
  const { user } = useAuth();
  return (
    <header style={{ background: HEADER_BG }}>
      <nav className="mx-auto max-w-6xl flex items-center gap-6 px-4 py-3">
        {/* Logo */}
        <Link
          href="/"
          className="font-semibold text-lg tracking-tight shrink-0 text-white hover:text-white/80 transition-colors"
        >
          Foreman
        </Link>

        {/* Nav links */}
        <div className="flex gap-5 text-sm text-white/60 flex-1">
          {NAV_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="hover:text-white transition-colors"
            >
              {label}
            </Link>
          ))}
        </div>

        {/* Right actions */}
        <div className="flex items-center gap-2">
          <a
            href="https://github.com/suyashisingh/Foreman"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-white/60 hover:text-white transition-colors mr-1"
          >
            GitHub
          </a>
          {user ? (
            <>
              <Link
                href="/dashboard"
                className="text-sm text-white/80 hover:text-white transition-colors rounded-full px-3 py-1 border border-white/20 hover:bg-white/10"
              >
                Dashboard
              </Link>
              <UserMenu />
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="text-sm text-white/80 hover:text-white transition-colors rounded-full px-3 py-1 border border-white/20 hover:bg-white/10"
              >
                Sign in
              </Link>
              <Link
                href="/register"
                className="text-sm text-white font-medium rounded-full px-4 py-1.5 transition-colors"
                style={{ background: "#C9A227" }}
              >
                Get started
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
