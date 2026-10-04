/**
 * app/page.tsx — Landing Page
 *
 * This is a React Server Component (the default in Next.js App Router).
 * Server Components render on the server — no JavaScript is sent to the
 * browser for this component itself. This makes the initial page load fast.
 *
 * When we need interactivity (click handlers, state), we will create
 * Client Components by adding "use client" at the top of the file.
 */

import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Home",
};

// ── Workflow steps shown on the landing page ──────────────────────────────────
const WORKFLOW_STEPS = [
  {
    step: "01",
    title: "Upload",
    description:
      "Upload supplier quotations in any format — PDF, Excel, or scanned documents.",
    icon: "📄",
  },
  {
    step: "02",
    title: "Extract",
    description:
      "AI extracts structured data: prices, VAT, delivery terms, warranty — validated against a strict schema.",
    icon: "🔍",
  },
  {
    step: "03",
    title: "Compare",
    description:
      "Deterministic backend computes Total Cost of Ownership. No LLM arithmetic — exact decimal calculations.",
    icon: "⚖️",
  },
  {
    step: "04",
    title: "Retrieve",
    description:
      "Semantic search finds relevant procurement policy clauses. Supplier history is queried from SQL.",
    icon: "📚",
  },
  {
    step: "05",
    title: "Verify",
    description:
      "A rule engine cross-validates the AI recommendation against company policy. Conflicts are flagged automatically.",
    icon: "✅",
  },
  {
    step: "06",
    title: "Approve",
    description:
      "A human reviews the evidence-backed recommendation and approves, rejects, or requests revision.",
    icon: "🔐",
  },
];

// ── Feature highlights ────────────────────────────────────────────────────────
const FEATURES = [
  {
    title: "Evidence-Backed Decisions",
    description:
      "Every recommendation is grounded in citations from policy documents, supplier history, and structured quote data. No hallucinated claims.",
    icon: "📎",
  },
  {
    title: "Deterministic Calculations",
    description:
      "TCO, VAT, and discount calculations are performed by backend code — not the LLM. Results are exact and auditable.",
    icon: "🧮",
  },
  {
    title: "Human-in-the-Loop",
    description:
      "AI prepares and explains. Humans decide. No procurement action is taken without explicit approval.",
    icon: "👤",
  },
  {
    title: "Full Audit Trail",
    description:
      "Every document upload, AI tool call, calculation, and approval is logged with a timestamp and actor.",
    icon: "📋",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* ── Navigation ───────────────────────────────────────────────────── */}
      <nav className="border-b border-[var(--color-border)] px-6 py-4">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center text-white font-bold text-sm">
              P
            </div>
            <span className="font-semibold text-lg text-[var(--color-text-primary)]">
              ProcureOps AI
            </span>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              Sign In
            </Link>
            <Link
              href="/register"
              className="rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="px-6 py-24 text-center">
        <div className="mx-auto max-w-4xl">
          {/* Badge */}
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-1.5">
            <span className="h-2 w-2 rounded-full bg-[var(--color-success)]" />
            <span className="text-xs text-[var(--color-text-secondary)]">
              AI-Assisted · Evidence-Backed · Human-Approved
            </span>
          </div>

          {/* Headline */}
          <h1 className="mb-6 text-5xl font-bold leading-tight tracking-tight text-[var(--color-text-primary)] md:text-6xl">
            Procurement decisions
            <br />
            <span className="text-[var(--color-accent)]">you can defend.</span>
          </h1>

          {/* Subheadline */}
          <p className="mx-auto mb-10 max-w-2xl text-lg text-[var(--color-text-secondary)] leading-relaxed">
            ProcureOps AI extracts, compares, and verifies supplier quotations
            against your company policies and supplier history — producing
            evidence-backed recommendations that a human can review and approve.
          </p>

          {/* CTAs */}
          <div className="flex items-center justify-center gap-4">
            <Link
              href="/register"
              className="rounded-lg bg-[var(--color-accent)] px-6 py-3 font-medium text-white hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              Start a free analysis
            </Link>
            <Link
              href="#workflow"
              className="rounded-lg border border-[var(--color-border)] px-6 py-3 font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-text-secondary)] transition-colors"
            >
              See how it works
            </Link>
          </div>
        </div>
      </section>

      {/* ── Workflow Steps ────────────────────────────────────────────────── */}
      <section id="workflow" className="px-6 py-20 border-t border-[var(--color-border)]">
        <div className="mx-auto max-w-7xl">
          <div className="mb-16 text-center">
            <h2 className="mb-4 text-3xl font-bold text-[var(--color-text-primary)]">
              From quote to decision in minutes
            </h2>
            <p className="text-[var(--color-text-secondary)]">
              A structured, auditable workflow — not a black-box chatbot.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {WORKFLOW_STEPS.map((item) => (
              <div
                key={item.step}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6"
              >
                <div className="mb-4 flex items-center gap-3">
                  <span className="text-2xl">{item.icon}</span>
                  <span className="text-xs font-mono font-bold text-[var(--color-accent)]">
                    {item.step}
                  </span>
                </div>
                <h3 className="mb-2 text-lg font-semibold text-[var(--color-text-primary)]">
                  {item.title}
                </h3>
                <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────────────────── */}
      <section className="px-6 py-20 border-t border-[var(--color-border)]">
        <div className="mx-auto max-w-7xl">
          <div className="mb-16 text-center">
            <h2 className="mb-4 text-3xl font-bold text-[var(--color-text-primary)]">
              Built on the right principles
            </h2>
            <p className="text-[var(--color-text-secondary)]">
              LLMs interpret and orchestrate. Deterministic systems calculate and verify.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            {FEATURES.map((feature) => (
              <div
                key={feature.title}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6"
              >
                <div className="mb-3 text-3xl">{feature.icon}</div>
                <h3 className="mb-2 text-lg font-semibold text-[var(--color-text-primary)]">
                  {feature.title}
                </h3>
                <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA Banner ───────────────────────────────────────────────────── */}
      <section className="px-6 py-20 border-t border-[var(--color-border)]">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="mb-4 text-3xl font-bold text-[var(--color-text-primary)]">
            Ready to make better procurement decisions?
          </h2>
          <p className="mb-8 text-[var(--color-text-secondary)]">
            Start with your first RFQ. Upload supplier quotes and get an
            evidence-backed recommendation in minutes.
          </p>
          <Link
            href="/register"
            className="inline-block rounded-lg bg-[var(--color-accent)] px-8 py-3 font-medium text-white hover:bg-[var(--color-accent-hover)] transition-colors"
          >
            Create your account
          </Link>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="border-t border-[var(--color-border)] px-6 py-8">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <p className="text-sm text-[var(--color-text-secondary)]">
            ProcureOps AI — Phase 1 (Development Foundation)
          </p>
          <p className="text-xs text-[var(--color-text-secondary)]">
            Built to learn. Built to last.
          </p>
        </div>
      </footer>
    </div>
  );
}
