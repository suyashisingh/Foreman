"use client";

import { useEffect, useRef, useState } from "react";
import { LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

export function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleMouseDown(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, [open]);

  if (!user) return null;

  const initial = user.email.charAt(0).toUpperCase();

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="User menu"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        {initial}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1.5 w-56 rounded-lg border border-border bg-popover text-popover-foreground shadow-lg py-1 z-50 animate-in fade-in-0 zoom-in-95 duration-150"
        >
          <div className="px-3 py-2 text-xs text-muted-foreground truncate">
            {user.email}
          </div>
          <div className="my-1 h-px bg-border" />
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              logout();
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-muted transition-colors text-left"
          >
            <LogOut size={13} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
