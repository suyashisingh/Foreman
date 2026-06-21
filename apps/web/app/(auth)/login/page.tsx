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
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>
            Enter your credentials to access Foreman.
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
        </CardContent>
      </Card>
    </div>
  );
}
