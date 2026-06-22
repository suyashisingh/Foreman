"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api-client";

function validateEmail(value: string): string | null {
  if (!value) return null;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
    ? null
    : "Enter a valid email address.";
}

function validatePassword(value: string): string | null {
  if (!value) return null;
  return value.length >= 8 ? null : "Password must be at least 8 characters.";
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
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Create account</CardTitle>
          <CardDescription>
            Sign up to start running agents on Foreman.
          </CardDescription>
        </CardHeader>
        <CardContent>
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
        </CardContent>
      </Card>
    </div>
  );
}
