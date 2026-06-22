"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  PlayCircle,
  BarChart3,
  BookOpen,
  Settings,
  LogOut,
  LogIn,
} from "lucide-react";
import { motion } from "framer-motion";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

const MAIN_NAV = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard", exact: true },
  { href: "/runs", icon: PlayCircle, label: "Runs", exact: false },
  { href: "/benchmark", icon: BarChart3, label: "Benchmark", exact: false },
  { href: "/about", icon: BookOpen, label: "About", exact: false },
] as const;

function isActive(href: string, pathname: string, exact: boolean) {
  return exact ? pathname === href : pathname.startsWith(href);
}

function SidebarLink({
  href,
  icon: Icon,
  label,
  active,
}: {
  href: string;
  icon: React.ElementType;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
        active
          ? "text-[#D4A820] font-medium"
          : "text-white/60 hover:text-white hover:bg-white/10",
      )}
    >
      {/* Sliding active-state background — spring physics via layoutId. */}
      {active && (
        <motion.div
          layoutId="sidebar-nav-highlight"
          className="absolute inset-0 rounded-md bg-[#D4A820]/20"
          transition={{ type: "spring", stiffness: 380, damping: 32 }}
        />
      )}
      <Icon size={16} className="relative z-10 shrink-0" />
      <span className="relative z-10 hidden lg:block">{label}</span>
    </Link>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <>
      {/* Desktop / tablet sidebar */}
      <aside className="hidden md:flex md:flex-col md:fixed md:inset-y-0 md:left-0 md:z-30 md:w-14 lg:w-56 border-r border-white/10 bg-[#28363C]">
        {/* Logo */}
        <div className="flex items-center gap-2 px-3 py-4 border-b border-white/10">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#D4A820] text-[#28363C] text-xs font-bold">
            F
          </span>
          <Link
            href="/dashboard"
            className="hidden lg:block font-semibold text-base tracking-tight text-white hover:text-white/80 transition-colors"
          >
            Foreman
          </Link>
        </div>

        {/* Main nav */}
        <nav className="flex-1 space-y-0.5 px-2 py-3">
          {MAIN_NAV.map((item) => (
            <SidebarLink
              key={item.href}
              href={item.href}
              icon={item.icon}
              label={item.label}
              active={isActive(item.href, pathname, item.exact)}
            />
          ))}
        </nav>

        {/* Settings */}
        <div className="border-t border-white/10 px-2 py-2">
          <SidebarLink
            href="/settings"
            icon={Settings}
            label="Settings"
            active={pathname === "/settings"}
          />
        </div>

        {/* User section — only when authenticated */}
        {user ? (
          <div className="border-t border-white/10 px-2 py-3 space-y-1">
            <div className="flex items-center gap-2 px-3 py-1">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#D4A820] text-[#28363C] text-xs font-medium">
                {user.email[0].toUpperCase()}
              </span>
              <span className="hidden lg:block text-xs text-white/50 truncate">
                {user.email}
              </span>
            </div>
            <button
              onClick={logout}
              className="flex w-full items-center gap-3 rounded-md px-3 py-1.5 text-sm text-white/50 hover:text-white hover:bg-white/10 transition-colors"
            >
              <LogOut size={14} className="shrink-0" />
              <span className="hidden lg:block">Sign out</span>
            </button>
          </div>
        ) : (
          <div className="border-t border-white/10 px-2 py-3">
            <SidebarLink
              href="/login"
              icon={LogIn}
              label="Sign in"
              active={false}
            />
          </div>
        )}
      </aside>

      {/* Mobile top bar */}
      <header className="md:hidden sticky top-0 z-20 border-b border-white/10 bg-[#28363C] px-4 py-2 flex items-center gap-4">
        <Link href="/" className="font-semibold text-sm shrink-0 text-white hover:text-white/80 transition-colors">
          Foreman
        </Link>
        <div className="flex gap-3 text-sm text-white/60 flex-1 overflow-x-auto">
          {MAIN_NAV.map(({ href, label, exact }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "whitespace-nowrap hover:text-white transition-colors",
                isActive(href, pathname, exact) && "text-[#D4A820] font-medium",
              )}
            >
              {label}
            </Link>
          ))}
          <Link
            href="/settings"
            className={cn(
              "whitespace-nowrap hover:text-white transition-colors",
              pathname === "/settings" && "text-[#D4A820] font-medium",
            )}
          >
            Settings
          </Link>
        </div>
        {user ? (
          <button
            onClick={logout}
            className="text-xs text-white/60 hover:text-white transition-colors shrink-0"
          >
            Sign out
          </button>
        ) : (
          <Link
            href="/login"
            className="text-xs text-white/60 hover:text-white transition-colors shrink-0"
          >
            Sign in
          </Link>
        )}
      </header>
    </>
  );
}
