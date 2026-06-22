"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api-client";

const DARK = "#28363C";
const GOLD = "#D4A820";

function categoriseError(err: unknown): { message: string; hint?: string } {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 403) {
      return {
        message: err.detail,
        hint: "Double-check your email and password.",
      };
    }
    if (err.status === 422) {
      return {
        message: "Invalid email or password format.",
        hint: "Email must be a valid address; password cannot be empty.",
      };
    }
    return { message: err.detail };
  }
  if (err instanceof TypeError && String(err).includes("fetch")) {
    return {
      message: "Connection error.",
      hint: "Make sure the Foreman API is running.",
    };
  }
  return { message: "An unexpected error occurred. Please try again." };
}

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const [pending, setPending] = useState(false);

  function validateEmail(value: string) {
    if (!value) return null;
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
      ? null
      : "Enter a valid email address.";
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const emailErr = validateEmail(email);
    if (emailErr) {
      setEmailError(emailErr);
      return;
    }
    setError(null);
    setPending(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError(categoriseError(err));
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
          AI-powered software engineering that ships — with every change
          verified against a real test suite.
        </p>

        {/* Proof points */}
        <div className="space-y-3">
          {[
            {
              title: "Four agents. One pipeline.",
              desc: "Planner, Coder, Tester, and Reviewer work in sequence inside a LangGraph graph.",
            },
            {
              title: "Isolated e2b sandboxes.",
              desc: "No code runs on your machine — every run executes in a fresh cloud environment.",
            },
            {
              title: "Human-in-the-loop approval.",
              desc: "You review every diff before anything merges. The agent stops and waits.",
            },
          ].map(({ title, desc }) => (
            <div
              key={title}
              className="rounded-lg px-4 py-3"
              style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.10)" }}
            >
              <p className="text-sm font-semibold text-white">{title}</p>
              <p className="mt-0.5 text-xs text-white/55">{desc}</p>
            </div>
          ))}
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
          <h1 className="font-heading text-2xl font-bold mb-1">Sign in</h1>
          <p className="text-sm text-muted-foreground mb-7">
            Enter your credentials to access Foreman.
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
                aria-describedby={emailError ? "email-error" : undefined}
              />
              {emailError && (
                <p id="email-error" className="text-xs text-destructive">
                  {emailError}
                </p>
              )}
            </div>

            <div className="space-y-1">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
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
                <div className="text-sm">
                  <p className="text-destructive">{error.message}</p>
                  {error.hint && (
                    <p className="text-destructive/70 text-xs mt-0.5">
                      {error.hint}
                    </p>
                  )}
                </div>
              </div>
            )}

            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            No account?{" "}
            <Link
              href="/register"
              className="font-medium text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
            >
              Create one →
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}
