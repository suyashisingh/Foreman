"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { BenchmarkStats } from "@/components/benchmark-stats";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api-client";

const DARK = "#28363C";
const GOLD = "#D4A820";

// ---------------------------------------------------------------------------
// Password strength
// ---------------------------------------------------------------------------

const PASSWORD_RULES = [
  { id: "length", label: "8+ characters", test: (p: string) => p.length >= 8 },
  {
    id: "upper",
    label: "Uppercase letter",
    test: (p: string) => /[A-Z]/.test(p),
  },
  { id: "number", label: "Number", test: (p: string) => /[0-9]/.test(p) },
  {
    id: "special",
    label: "Special character",
    test: (p: string) => /[^A-Za-z0-9]/.test(p),
  },
];

function PasswordStrengthHints({ password }: { password: string }) {
  if (!password) return null;
  return (
    <ul className="mt-1 space-y-0.5">
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(password);
        return (
          <li
            key={rule.id}
            className={`flex items-center gap-1 text-xs ${ok ? "text-green-600 dark:text-green-500" : "text-muted-foreground"}`}
          >
            <span aria-hidden>{ok ? "✓" : "○"}</span>
            {rule.label}
          </li>
        );
      })}
    </ul>
  );
}

function validateEmail(value: string): string | null {
  if (!value) return null;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
    ? null
    : "Enter a valid email address.";
}

function validatePassword(value: string): string | null {
  if (!value) return null;
  const failing = PASSWORD_RULES.filter((r) => !r.test(value));
  return failing.length === 0 ? null : "Password does not meet all requirements.";
}

function validateConfirm(password: string, confirm: string): string | null {
  if (!confirm) return null;
  return password === confirm ? null : "Passwords do not match.";
}

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const eErr = validateEmail(email);
    const pErr = validatePassword(password);
    const cErr = validateConfirm(password, confirm);
    setEmailError(eErr);
    setPasswordError(pErr);
    setConfirmError(cErr);
    if (eErr || pErr || cErr) return;

    setError(null);
    setPending(true);
    try {
      await register(email, password);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409 || err.detail.toLowerCase().includes("exist")) {
          setError("An account with this email already exists.");
        } else {
          setError(err.detail);
        }
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-60px)]">
      {/* Left panel — brand + stats, hidden on mobile */}
      <div
        className="hidden md:flex md:w-2/5 flex-col justify-center px-10 py-16 shrink-0"
        style={{ background: DARK }}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 mb-10">
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-sm font-bold"
            style={{ background: GOLD, color: DARK }}
          >
            F
          </span>
          <span className="font-semibold text-lg text-white tracking-tight">
            Foreman
          </span>
        </div>

        {/* Tagline */}
        <h2 className="font-heading font-bold text-2xl text-white leading-snug mb-4">
          Autonomous agents.<br />
          Real code.<br />
          Measured results.
        </h2>
        <p className="text-white/50 text-sm leading-relaxed mb-10">
          Deploy your first AI engineering run in under five minutes. Just
          paste a public repo URL and describe the issue.
        </p>

        {/* Live benchmark numbers */}
        <div className="space-y-3">
          <p
            className="text-xs font-mono uppercase tracking-widest"
            style={{ color: GOLD }}
          >
            Live Benchmark
          </p>
          <div className="text-white [&_p]:text-white/60 [&_.font-bold]:text-white">
            <BenchmarkStats variant="grid" />
          </div>
        </div>
      </div>

      {/* Right panel — form */}
      <div className="flex-1 flex items-center justify-center bg-white px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.28, ease: "easeOut" }}
          className="w-full max-w-sm"
        >
          <h1 className="font-heading text-2xl font-bold mb-1">Create account</h1>
          <p className="text-sm text-muted-foreground mb-7">
            Sign up to start running agents on Foreman.
          </p>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-1">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                placeholder="you@example.com"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (emailError) setEmailError(validateEmail(e.target.value));
                }}
                onBlur={() => setEmailError(validateEmail(email))}
                aria-invalid={emailError != null}
              />
              {emailError && (
                <p className="text-xs text-destructive">{emailError}</p>
              )}
            </div>

            <div className="space-y-1">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (passwordError)
                    setPasswordError(validatePassword(e.target.value));
                  if (confirmError)
                    setConfirmError(validateConfirm(e.target.value, confirm));
                }}
                onBlur={() => setPasswordError(validatePassword(password))}
                aria-invalid={passwordError != null}
              />
              <PasswordStrengthHints password={password} />
              {passwordError && (
                <p className="text-xs text-destructive">{passwordError}</p>
              )}
            </div>

            <div className="space-y-1">
              <label htmlFor="confirm" className="text-sm font-medium">
                Confirm password
              </label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                required
                placeholder="••••••••"
                value={confirm}
                onChange={(e) => {
                  setConfirm(e.target.value);
                  if (confirmError)
                    setConfirmError(validateConfirm(password, e.target.value));
                }}
                onBlur={() =>
                  setConfirmError(validateConfirm(password, confirm))
                }
                aria-invalid={confirmError != null}
              />
              {confirmError && (
                <p className="text-xs text-destructive">{confirmError}</p>
              )}
            </div>

            {error && (
              <div
                className="flex items-start gap-2 rounded-md bg-destructive/10 border border-destructive/20 px-3 py-2"
                role="alert"
              >
                <AlertCircle
                  size={14}
                  className="text-destructive mt-0.5 shrink-0"
                />
                <p className="text-sm text-destructive">{error}</p>
              </div>
            )}

            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? "Creating account…" : "Create account"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link
              href="/login"
              className="font-medium text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
            >
              Sign in →
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}
