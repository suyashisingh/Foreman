"use client";

import { motion, type Variants } from "framer-motion";
import { Bot, BarChart3, Radio } from "lucide-react";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Design tokens
// ---------------------------------------------------------------------------

const DARK = "#28363C";  // dark slate-teal — hero, features, how-it-works
const CREAM = "#F5F2EC"; // warm cream — live results, step cards
const GOLD = "#D4A820"; // warm golden yellow — CTA band, eyebrow labels, accent

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.30, ease: "easeOut" } },
};

const stagger = (delay = 0.08): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren: delay } },
});

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function Eyebrow({
  code,
  label,
  dark = false,
}: {
  code: string;
  label: string;
  dark?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div
        className="h-px w-8 shrink-0"
        style={{ background: dark ? "rgba(201,84,42,0.5)" : GOLD + "80" }}
      />
      <span
        className="font-mono text-xs uppercase tracking-widest"
        style={{ color: GOLD }}
      >
        {code} · {label}
      </span>
    </div>
  );
}

// Feature card used in the "What it does" section
function FeatureCard({
  id,
  icon: Icon,
  title,
  description,
}: {
  id: string;
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <motion.div
      variants={fadeUp}
      className="relative rounded-xl border p-5 h-full hover:shadow-md transition-shadow"
      style={{ borderColor: "#d6d0c8", background: "#fff" }}
    >
      {/* Monospace ID in top-right corner */}
      <span className="absolute top-3 right-3 font-mono text-[10px] text-gray-400">
        {id}
      </span>
      <div
        className="mb-3 flex h-8 w-8 items-center justify-center rounded-md"
        style={{ background: GOLD + "15" }}
      >
        <Icon size={16} style={{ color: GOLD }} />
      </div>
      <p className="font-heading font-semibold text-sm mb-1">{title}</p>
      <p className="text-xs text-muted-foreground leading-relaxed">
        {description}
      </p>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function HomePage() {
  return (
    <div className="flex flex-col">

      {/* ── Section 1: HERO — dark teal ─────────────────────────────── */}
      <section style={{ background: DARK }} className="relative overflow-hidden">
        {/* Soft ambient glow — decorative */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-0 left-1/2 -translate-x-1/2 h-64 w-[600px] rounded-full blur-[100px]"
          style={{ background: `${GOLD}18` }}
        />

        <motion.div
          variants={stagger(0.07)}
          initial="hidden"
          animate="show"
          className="relative mx-auto max-w-5xl px-4 py-24 space-y-6"
        >
          <motion.div variants={fadeUp}>
            <Eyebrow
              code="FM-00"
              label="AUTONOMOUS MULTI-AGENT PLATFORM · BUILT SOLO"
              dark
            />
            <h1 className="font-heading font-bold text-5xl leading-tight text-white">
              Foreman
            </h1>
            <p
              className="font-heading text-2xl mt-2 text-white/80 leading-snug"
            >
              Four agents. One sandbox.{" "}
              <em className="italic" style={{ color: GOLD }}>
                Actually
              </em>{" "}
              measured.
            </p>
          </motion.div>

          <motion.p
            variants={fadeUp}
            className="text-base text-white/65 max-w-xl leading-relaxed"
          >
            Give it a GitHub issue — the Planner, Coder, Tester, and Reviewer
            agents handle the rest in an isolated cloud environment. You see the
            diff and approve before anything merges.
          </motion.p>

          <motion.p
            variants={fadeUp}
            className="text-sm text-white/45 max-w-lg"
          >
            LangGraph orchestration · Coder↔Tester self-correction loop (up to
            3×) · pgvector RAG · live WebSocket streaming · human-in-the-loop
            approval gate.
          </motion.p>

          <motion.div
            variants={fadeUp}
            className="flex gap-3 flex-wrap pt-2"
          >
            <Link
              href="/register"
              className="text-sm font-medium text-white rounded-full px-5 py-2.5 transition-opacity hover:opacity-90"
              style={{ background: GOLD }}
            >
              Get started
            </Link>
            <Link
              href="/login"
              className="text-sm font-medium text-white/80 rounded-full px-5 py-2.5 border transition-colors hover:text-white hover:bg-white/10"
              style={{ borderColor: "rgba(255,255,255,0.2)" }}
            >
              Sign in
            </Link>
            <Link
              href="/benchmark"
              className="text-sm font-medium text-white/60 rounded-full px-5 py-2.5 transition-colors hover:text-white"
            >
              Benchmark Results →
            </Link>
          </motion.div>
        </motion.div>
      </section>

      {/* ── Section 2: WHAT IT DOES — cream ─────────────────────────── */}
      <section style={{ background: CREAM }}>
        <div className="mx-auto max-w-5xl px-4 py-20 space-y-8">
          <motion.div
            variants={stagger(0.07)}
            initial="hidden"
            animate="show"
          >
            <motion.div variants={fadeUp}>
              <Eyebrow code="S-01" label="WHAT IT DOES" />
              <h2 className="font-heading font-bold text-3xl text-[#1e2a2e]">
                Built to handle{" "}
                <em className="italic" style={{ color: GOLD }}>
                  real
                </em>{" "}
                tasks.
              </h2>
            </motion.div>

            <motion.div
              variants={stagger(0.1)}
              initial="hidden"
              animate="show"
              className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3"
            >
              <FeatureCard
                id="WF-01"
                icon={Bot}
                title="Plan & Execute"
                description="LangGraph agents decompose issues into step-by-step plans, then implement them in isolated e2b cloud sandboxes — no local execution, no shared state."
              />
              <FeatureCard
                id="WF-02"
                icon={Radio}
                title="Live Trace"
                description="Stream agent steps, tool calls, and diffs in real time over WebSocket. Watch the model think, write, and self-correct across up to three retry loops."
              />
              <FeatureCard
                id="WF-03"
                icon={BarChart3}
                title="Measured Results"
                description="Evaluated against real open-source repositories. pass@1 and pass@3 rates come from actual test runs — not self-reported benchmarks."
              />
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ── Section 3: HOW IT WORKS — dark teal ─────────────────────── */}
      <section style={{ background: DARK }}>
        <div className="mx-auto max-w-5xl px-4 py-20 space-y-8">
          <motion.div
            variants={stagger(0.06)}
            initial="hidden"
            animate="show"
          >
            <motion.div variants={fadeUp}>
              <Eyebrow code="S-02" label="HOW IT WORKS" dark />
              <h2 className="font-heading font-bold text-3xl text-white">
                How it{" "}
                <em className="italic" style={{ color: GOLD }}>
                  works
                </em>
              </h2>
              <p className="mt-2 text-sm text-white/60 max-w-lg">
                Four specialised agents run in sequence inside a LangGraph
                graph. Each has exactly one responsibility.
              </p>
            </motion.div>

            <motion.div
              variants={stagger(0.08)}
              initial="hidden"
              animate="show"
              className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-3"
            >
              {[
                {
                  n: "AG-01",
                  name: "Planner",
                  desc: "Searches the codebase with pgvector RAG, then writes a step-by-step implementation plan — which files to touch and why.",
                },
                {
                  n: "AG-02",
                  name: "Coder",
                  desc: "Executes the plan with file-editing tool calls inside an isolated e2b cloud sandbox. Never runs on your machine.",
                },
                {
                  n: "AG-03",
                  name: "Tester",
                  desc: "Runs pytest. On failure, sends the full output back to Coder for targeted fixes — up to 3 loops. This is the self-correction loop.",
                },
                {
                  n: "AG-04",
                  name: "Reviewer",
                  desc: "Assesses risk (low/medium/high), writes a PR title and description, and presents the diff for your approval or rejection.",
                },
              ].map(({ n, name, desc }) => (
                <motion.div
                  key={n}
                  variants={fadeUp}
                  className="flex gap-3 rounded-lg p-4"
                  style={{ border: "1px solid rgba(255,255,255,0.10)", background: "rgba(255,255,255,0.04)" }}
                >
                  <span
                    className="shrink-0 font-mono text-[10px] rounded px-1.5 py-1 h-fit mt-0.5"
                    style={{ color: GOLD, background: `${GOLD}18` }}
                  >
                    {n}
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-white">{name}</p>
                    <p className="mt-0.5 text-sm text-white/55">{desc}</p>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ── Section 4: CTA BAND — gold ──────────────────────────────── */}
      <section style={{ background: GOLD }}>
        <motion.div
          variants={stagger(0.07)}
          initial="hidden"
          animate="show"
          className="mx-auto max-w-5xl px-4 py-20 space-y-5"
        >
          <motion.div variants={fadeUp}>
            <Eyebrow code="S-03" label="GET STARTED" />
            <h2 className="font-heading font-bold text-3xl text-white">
              Ready to see it{" "}
              <em className="italic" style={{ color: "rgba(255,255,255,0.75)" }}>
                work
              </em>
              ?
            </h2>
            <p className="mt-2 text-sm text-white/70 max-w-sm">
              Register a GitHub repo and submit your first issue in under two
              minutes.
            </p>
          </motion.div>
          <motion.div variants={fadeUp} className="flex gap-3 flex-wrap">
            <Link
              href="/register"
              className="text-sm font-semibold text-[#28363C] bg-white rounded-full px-5 py-2.5 hover:bg-white/90 transition-colors"
            >
              Create an account
            </Link>
            <Link
              href="/about"
              className="text-sm font-medium text-white/80 rounded-full px-5 py-2.5 border border-white/30 hover:text-white hover:bg-white/10 transition-colors"
            >
              Read the architecture →
            </Link>
          </motion.div>
        </motion.div>
      </section>

    </div>
  );
}
