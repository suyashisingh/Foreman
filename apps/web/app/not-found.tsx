import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-24 flex flex-col items-center text-center space-y-6">
      <p className="text-6xl font-bold tracking-tight text-muted-foreground/40">
        404
      </p>
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Page not found
        </h1>
        <p className="text-muted-foreground max-w-sm">
          The page you&apos;re looking for doesn&apos;t exist or has been
          moved.
        </p>
      </div>
      <div className="flex gap-3">
        <Link href="/" className={cn(buttonVariants())}>
          Go home
        </Link>
        <Link
          href="/dashboard"
          className={cn(buttonVariants({ variant: "outline" }))}
        >
          Dashboard
        </Link>
      </div>
    </div>
  );
}
