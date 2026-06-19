// TODO (auth backend — Day 2): Wire the form to POST /auth/register.
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

export default function RegisterPage() {
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
                autoComplete="new-password"
                required
                placeholder="••••••••"
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="confirm" className="text-sm font-medium">
                Confirm password
              </label>
              <Input
                id="confirm"
                name="confirm"
                type="password"
                autoComplete="new-password"
                required
                placeholder="••••••••"
              />
            </div>

            <Button type="submit" className="w-full">
              Create account
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/login" className="underline hover:text-foreground">
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
