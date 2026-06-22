"use client";

import { usePathname } from "next/navigation";
import { AuthGuard } from "@/components/auth-guard";
import { AppSidebar } from "@/components/app-sidebar";

// /about and /benchmark live in this route group so authenticated users always
// see the sidebar — but they're public content that doesn't require a JWT.
const PUBLIC_ROUTES = new Set(["/about", "/benchmark"]);

export default function AppGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isPublic = PUBLIC_ROUTES.has(pathname);

  const content = (
    <div className="flex min-h-screen">
      <AppSidebar />
      <main
        key={pathname}
        className="flex-1 min-w-0 md:ml-14 lg:ml-56 animate-[page-fadein_200ms_ease-out_both]"
      >
        {children}
      </main>
    </div>
  );

  return isPublic ? content : <AuthGuard>{content}</AuthGuard>;
}
