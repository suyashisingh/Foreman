"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: string;
  message: string;
  variant: ToastVariant;
}

interface ToastCtx {
  addToast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastCtx | null>(null);

// Safe to call outside a ToastProvider — returns a no-op so pages/tests don't
// need to render the provider to use components that call useToast().
export function useToast(): ToastCtx {
  return useContext(ToastContext) ?? { addToast: () => {} };
}

const VARIANT_STYLES: Record<
  ToastVariant,
  {
    cls: string;
    Icon: React.ComponentType<{ size?: number; className?: string }>;
  }
> = {
  success: {
    cls: "border-green-200 bg-green-50 text-green-900 dark:bg-green-950/60 dark:border-green-800 dark:text-green-100",
    Icon: CheckCircle2,
  },
  error: {
    cls: "border-destructive/30 bg-destructive/10 text-destructive",
    Icon: XCircle,
  },
  info: {
    cls: "border-border bg-background text-foreground shadow-sm",
    Icon: Info,
  },
};

function ToastBubble({
  toast,
  onDismiss,
}: {
  toast: ToastItem;
  onDismiss: (id: string) => void;
}) {
  const { cls, Icon } = VARIANT_STYLES[toast.variant];
  return (
    <div
      className={cn(
        "pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 text-sm shadow-md max-w-sm",
        "animate-in slide-in-from-bottom-2 duration-200",
        cls,
      )}
    >
      <Icon size={15} className="mt-0.5 shrink-0" />
      <span className="flex-1">{toast.message}</span>
      <button
        onClick={() => onDismiss(toast.id)}
        className="mt-0.5 shrink-0 opacity-50 hover:opacity-100 transition-opacity"
        aria-label="Dismiss"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback(
    (message: string, variant: ToastVariant = "info") => {
      const id = Math.random().toString(36).slice(2);
      setToasts((prev) => [...prev, { id, message, variant }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4000);
    },
    [],
  );

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      {/* Toast container — fixed bottom-right, above everything else */}
      <div
        aria-live="polite"
        aria-label="Notifications"
        className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
      >
        {toasts.map((t) => (
          <ToastBubble key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
