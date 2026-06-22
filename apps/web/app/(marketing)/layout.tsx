import Link from "next/link";
import { MarketingHeader } from "@/components/marketing-header";

function MarketingFooter() {
  return (
    <footer style={{ background: "#28363C" }}>
      <div className="mx-auto max-w-6xl px-4 py-10 grid grid-cols-1 sm:grid-cols-3 gap-8">
        {/* Brand */}
        <div className="space-y-2">
          <p className="font-semibold text-white text-base tracking-tight">Foreman</p>
          <p className="text-xs text-white/50 font-mono leading-relaxed">
            AUTONOMOUS MULTI-AGENT<br />
            SOFTWARE ENGINEERING
          </p>
        </div>

        {/* Navigate */}
        <div className="space-y-2">
          <p className="font-mono text-xs text-white/40 uppercase tracking-widest">
            Navigate
          </p>
          <div className="space-y-1.5">
            {[
              { href: "/", label: "Home" },
              { href: "/about", label: "About" },
              { href: "/benchmark", label: "Benchmark" },
              { href: "/register", label: "Get started" },
            ].map(({ href, label }) => (
              <div key={href}>
                <Link
                  href={href}
                  className="text-sm text-white/60 hover:text-white transition-colors"
                >
                  {label}
                </Link>
              </div>
            ))}
          </div>
        </div>

        {/* Reach us */}
        <div className="space-y-2">
          <p className="font-mono text-xs text-white/40 uppercase tracking-widest">
            Reach us
          </p>
          <div className="space-y-1.5">
            <div>
              <a
                href="https://github.com/suyashisingh/Foreman"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-white/60 hover:text-white transition-colors"
              >
                GitHub
              </a>
            </div>
          </div>
          <p className="text-xs text-white/30 pt-2">
            Portfolio project by Suyash Singh
          </p>
        </div>
      </div>
    </footer>
  );
}

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <MarketingHeader />
      <main className="flex-1">{children}</main>
      <MarketingFooter />
    </>
  );
}
