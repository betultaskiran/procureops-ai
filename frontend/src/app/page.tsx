import type { Metadata } from "next";
import { ThemeToggle } from "@/components/theme-toggle";
import Link from "next/link";
import { 
  FileText, 
  ScanText, 
  Calculator, 
  ShieldCheck, 
  BrainCircuit, 
  CheckCircle, 
  UserCheck, 
  ArrowRight
} from "lucide-react";

export const metadata: Metadata = {
  title: "ProcureOps | Enterprise AI Procurement",
  description: "B2B AI-powered procurement decision and workflow platform.",
};

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-bg text-text-primary flex flex-col font-sans selection:bg-primary/20">
      {/* ── Navbar ──────────────────────────────────────────────────────── */}
      <header className="border-b border-border px-8 py-4 sticky top-0 bg-bg/80 backdrop-blur-md z-50">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded bg-primary flex items-center justify-center text-white font-bold text-lg shadow-sm">
              P
            </div>
            <span className="font-semibold tracking-tight text-xl">ProcureOps</span>
          </div>
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-text-muted">
            <Link href="/dashboard" className="hover:text-primary transition-colors">Product</Link>
            <Link href="/rfqs" className="hover:text-primary transition-colors">Features</Link>
            <Link href="/policies" className="hover:text-primary transition-colors">How it Works</Link>
          </nav>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <Link 
              href="/dashboard"
              className="bg-primary hover:bg-primary-hover text-white px-5 py-2 rounded-md font-medium transition-all shadow-sm text-sm"
            >
              Get Started
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center w-full">
        
        {/* ── Hero Section ────────────────────────────────────────────────── */}
        <section className="w-full max-w-7xl mx-auto px-8 pt-24 pb-16 flex flex-col lg:flex-row items-center gap-16 relative">
          {/* Subtle Grid Background */}
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] -z-10" />

          {/* Left Text */}
          <div className="flex-1 text-center lg:text-left">
            <h1 className="text-5xl lg:text-6xl font-semibold tracking-tight leading-[1.1] mb-6 text-text-primary">
              Turn supplier quotes into <br className="hidden lg:block" />
              <span className="text-primary">confident procurement decisions.</span>
            </h1>
            <p className="text-lg text-text-muted leading-relaxed max-w-2xl mx-auto lg:mx-0 mb-10">
              ProcureOps combines AI, policy intelligence and real-time data to help you find the best suppliers, manage risks and streamline your procurement workflow.
            </p>
            <div className="flex items-center justify-center lg:justify-start gap-4">
              <Link 
                href="/dashboard"
                className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-6 py-3 rounded-md font-medium transition-all shadow-sm"
              >
                Get Started
                <ArrowRight size={18} />
              </Link>
              <button className="flex items-center gap-2 bg-surface border border-border hover:border-text-muted text-text-primary px-6 py-3 rounded-md font-medium transition-all shadow-sm">
                <ScanText size={18} />
                Watch Demo
              </button>
            </div>
          </div>

          {/* Right Visual (Workflow Graphic Coded in Tailwind) */}
          <div className="flex-1 w-full max-w-lg relative">
            <div className="relative flex flex-col gap-6">
              {/* Connecting Line */}
              <div className="absolute left-[39px] top-8 bottom-8 w-[2px] bg-border z-0" />
              
              <div className="relative z-10 flex items-center gap-6 group">
                <div className="h-20 w-20 rounded-full bg-surface border-2 border-border flex items-center justify-center shrink-0 shadow-sm group-hover:border-primary transition-colors">
                  <FileText className="text-text-muted group-hover:text-primary transition-colors" size={32} />
                </div>
                <div>
                  <h3 className="font-semibold text-lg">Supplier Quotes</h3>
                  <p className="text-text-muted text-sm">Upload RFQs & receive offers</p>
                </div>
              </div>

              <div className="relative z-10 flex items-center gap-6 group">
                <div className="h-20 w-20 rounded-full bg-surface border-2 border-ai/50 flex items-center justify-center shrink-0 shadow-sm group-hover:border-ai transition-colors">
                  <BrainCircuit className="text-ai" size={32} />
                </div>
                <div>
                  <h3 className="font-semibold text-lg text-ai">AI Analysis</h3>
                  <p className="text-text-muted text-sm">Evaluate TCO, compliance & risk</p>
                </div>
              </div>

              <div className="relative z-10 flex items-center gap-6 group">
                <div className="h-20 w-20 rounded-full bg-surface border-2 border-border flex items-center justify-center shrink-0 shadow-sm group-hover:border-primary transition-colors">
                  <ShieldCheck className="text-text-muted group-hover:text-primary transition-colors" size={32} />
                </div>
                <div>
                  <h3 className="font-semibold text-lg">Evidence</h3>
                  <p className="text-text-muted text-sm">See sources & reasoning</p>
                </div>
              </div>

              <div className="relative z-10 flex items-center gap-6 group">
                <div className="h-20 w-20 rounded-full bg-surface border-2 border-border flex items-center justify-center shrink-0 shadow-sm group-hover:border-primary transition-colors">
                  <UserCheck className="text-text-muted group-hover:text-primary transition-colors" size={32} />
                </div>
                <div>
                  <h3 className="font-semibold text-lg">Human Decision</h3>
                  <p className="text-text-muted text-sm">Approve and create PO</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Metrics ────────────────────────────────────────── */}
        <section className="w-full max-w-7xl mx-auto px-8 mb-24">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border border border-border rounded-xl overflow-hidden shadow-sm">
            <div className="bg-surface p-8 flex flex-col gap-2">
              <span className="text-sm font-medium text-text-muted uppercase tracking-wider">Faster Decisions</span>
              <span className="text-3xl font-semibold text-text-primary">%60</span>
              <span className="text-xs text-text-muted">less time to decision</span>
            </div>
            <div className="bg-surface p-8 flex flex-col gap-2">
              <span className="text-sm font-medium text-text-muted uppercase tracking-wider">Lower Costs</span>
              <span className="text-3xl font-semibold text-text-primary">%15</span>
              <span className="text-xs text-text-muted">average savings</span>
            </div>
            <div className="bg-surface p-8 flex flex-col gap-2">
              <span className="text-sm font-medium text-text-muted uppercase tracking-wider">Higher Compliance</span>
              <span className="text-3xl font-semibold text-text-primary">%98</span>
              <span className="text-xs text-text-muted">policy adherence</span>
            </div>
            <div className="bg-surface p-8 flex flex-col gap-2">
              <span className="text-sm font-medium text-text-muted uppercase tracking-wider">Audit Ready</span>
              <span className="text-3xl font-semibold text-text-primary">100%</span>
              <span className="text-xs text-text-muted">traceable decisions</span>
            </div>
          </div>
        </section>

        {/* ── Principles Section (Built on the right principles) ────────── */}
        <section className="w-full max-w-7xl mx-auto px-8 py-24 border-t border-border mt-12 mb-24">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-semibold mb-4 text-text-primary">Built on the right principles</h2>
            <p className="text-text-muted text-lg max-w-2xl mx-auto">LLMs interpret and orchestrate. Deterministic systems calculate and verify.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="bg-surface border border-border rounded-xl p-8 shadow-sm hover:shadow-md transition-all hover:-translate-y-1">
              <div className="h-12 w-12 rounded-lg bg-ai/10 text-ai border border-ai/20 flex items-center justify-center mb-6">
                <ShieldCheck size={24} />
              </div>
              <h3 className="text-xl font-semibold mb-3">Evidence-Backed Decisions</h3>
              <p className="text-text-muted leading-relaxed mb-6">
                Every recommendation is grounded in citations from policy documents, supplier history, and structured quote data.
              </p>
              <div className="flex justify-end mt-auto">
                <ArrowRight size={20} className="text-primary" />
              </div>
            </div>

            <div className="bg-surface border border-border rounded-xl p-8 shadow-sm hover:shadow-md transition-all hover:-translate-y-1">
              <div className="h-12 w-12 rounded-lg bg-primary/10 text-primary border border-primary/20 flex items-center justify-center mb-6">
                <Calculator size={24} />
              </div>
              <h3 className="text-xl font-semibold mb-3">Deterministic Calculations</h3>
              <p className="text-text-muted leading-relaxed mb-6">
                TCO, VAT, and discount calculations are performed by backend code — not the LLM. Results are exact and auditable.
              </p>
              <div className="flex justify-end mt-auto">
                <ArrowRight size={20} className="text-primary" />
              </div>
            </div>

            <div className="bg-surface border border-border rounded-xl p-8 shadow-sm hover:shadow-md transition-all hover:-translate-y-1">
              <div className="h-12 w-12 rounded-lg bg-text-primary/5 text-text-primary border border-border flex items-center justify-center mb-6">
                <UserCheck size={24} />
              </div>
              <h3 className="text-xl font-semibold mb-3">Human in the Loop</h3>
              <p className="text-text-muted leading-relaxed mb-6">
                AI prepares and explains. Final decisions are made by your team with full transparency and control.
              </p>
              <div className="flex justify-end mt-auto">
                <ArrowRight size={20} className="text-primary" />
              </div>
            </div>
          </div>
        </section>

      </main>
    </div>
  );
}
