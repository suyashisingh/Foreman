// TODO (auth backend — Day 2): Wire the form to POST /auth/login.
// The submit handler is currently a no-op; the auth backend does not exist yet.
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import Link from "next/link";

export default function LoginPage() {
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
          {/* form is UI-only; action is a no-op until auth backend exists */}
          <form className="space-y-4" action="#">
            <div className="space-y-1">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                placeholder="••••••••"
              />
            </div>

            <Button type="submit" className="w-full">
              Sign in
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            No account?{" "}
            <Link href="/register" className="underline hover:text-foreground">
              Register
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
