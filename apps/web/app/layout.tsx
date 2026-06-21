import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

// Typography decision: Geist (clean geometric sans-serif) for all text — body,
// UI, and headings. Headings use font-bold + tracking-tight for hierarchy.
// No heavy serifs — the product is a developer tool and should read like one.
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Foreman",
  description: "Autonomous multi-agent software engineering platform",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        {/* AppShell is a client component that provides AuthProvider,
            ToastProvider, and the top nav with user menu. Server component
            children (page content) are passed through as opaque RSC trees. */}
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
