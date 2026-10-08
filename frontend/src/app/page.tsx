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

const WORKFLOW_STEPS = [
  {
    title: "Supplier Quote",
    description: "PDF/Excel document ingestion",
    icon: FileText,
  },
  {
    title: "Data Extraction",
    description: "Structured schema generation",
    icon: ScanText,
  },
  {
    title: "TCO Calculation",
    description: "Deterministic cost modeling",
    icon: Calculator,
  },
  {
    title: "Policy Verification",
    description: "Hard rule compliance check",
    icon: ShieldCheck,
  },
  {
    title: "AI Analysis",
    description: "RAG & trade-off reasoning",
    icon: BrainCircuit,
  },
  {
    title: "Audit Match",
    description: "Evidence validation",
    icon: CheckCircle,
  },
  {
    title: "Human Approval",
    description: "Manager exception/sign-off",
    icon: UserCheck,
  },
];

const METRICS = [
  { label: "Quote Processing Time", value: "< 2s" },
  { label: "Deterministic Accuracy", value: "100%" },
  { label: "Policy Context Embedded", value: "Auto" },
  { label: "Hallucination Risk", value: "Blocked" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-bg text-text-primary flex flex-col relative overflow-hidden">
      {/* ── Subtle Background Grid ────────────────────────────────────────── */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] pointer-events-none" />

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
            <Link href="/dashboard" className="hover:text-primary transition-colors">Dashboard</Link>
            <Link href="/rfqs" className="hover:text-primary transition-colors">RFQs</Link>
            <Link href="/policies" className="hover:text-primary transition-colors">Policies</Link>
          </nav>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <Link 
              href="/dashboard"
              className="bg-primary hover:bg-primary-hover text-white px-5 py-2 rounded-md font-medium transition-colors text-sm shadow-sm"
            >
              Go to App
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero Section ────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col items-center pt-24 pb-16 px-6 relative z-10">
        
        <div className="text-center max-w-4xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-ai/10 border border-ai/20 text-ai text-xs font-semibold uppercase tracking-widest mb-6">
            <BrainCircuit size={14} />
            <span>AI-Powered Workflow Engine</span>
          </div>
          <h1 className="text-5xl md:text-6xl font-semibold tracking-tight leading-tight mb-6 text-text-primary">
            Enterprise procurement, <br />
            secured by deterministic logic <br />
            and powered by AI.
          </h1>
          <p className="text-lg text-text-muted leading-relaxed max-w-2xl mx-auto">
            ProcureOps combines structured quote extraction, exact financial calculations, 
            historical supplier memory, and AI reasoning. Every decision is backed by evidence 
            and awaits human approval.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
             <Link 
              href="/dashboard"
              className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-8 py-3 rounded-md text-sm font-medium transition-all shadow-md group"
            >
              Start Free Trial
              <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
            </Link>
            <button className="flex items-center gap-2 bg-surface hover:bg-surface-elevated border border-border text-text-primary px-8 py-3 rounded-md text-sm font-medium transition-all shadow-sm">
              Book a Demo
            </button>
          </div>
        </div>

        {/* ── Product UI Mockup (Hero Graphic) ──────────────────────────── */}
        <div className="w-full max-w-5xl mx-auto mb-24 relative perspective-[2000px]">
          <div className="absolute inset-0 bg-primary/5 blur-3xl rounded-full -z-10 transform -translate-y-10" />
          <div className="bg-surface border border-border rounded-xl shadow-2xl overflow-hidden flex flex-col ring-1 ring-border/50">
            {/* Mockup Header */}
            <div className="border-b border-border bg-surface-elevated px-4 py-3 flex items-center gap-4">
              <div className="flex gap-1.5">
                <div className="w-3 h-3 rounded-full bg-error/80" />
                <div className="w-3 h-3 rounded-full bg-warning/80" />
                <div className="w-3 h-3 rounded-full bg-success/80" />
              </div>
              <div className="text-xs font-medium text-text-muted flex-1 text-center font-mono">
                Analysis-2026-015 — Laptop & Accessories
              </div>
            </div>
            {/* Mockup Content */}
            <div className="p-6 grid grid-cols-3 gap-6 bg-bg/50">
              <div className="col-span-2 bg-surface border border-border rounded-lg p-5 shadow-sm">
                <h3 className="text-sm font-semibold mb-4 text-text-primary flex items-center justify-between">
                  Supplier Comparison
                  <span className="text-xs font-normal text-text-muted border border-border px-2 py-1 rounded bg-surface-elevated">View all</span>
                </h3>
                <div className="space-y-3">
                  {[
                    { name: "TechCorp", tco: "407,200 TRY", dev: "10 days", status: "Recommended", statusColor: "bg-success/10 text-success border-success/20" },
                    { name: "AlphaTech", tco: "450,800 TRY", dev: "8 days", status: "Pass", statusColor: "bg-border text-text-muted border-border" },
                    { name: "GlobalTech", tco: "512,300 TRY", dev: "12 days", status: "Warning", statusColor: "bg-warning/10 text-warning border-warning/20" },
                  ].map((s, i) => (
                    <div key={i} className="flex items-center justify-between text-sm py-2 border-b border-border last:border-0">
                      <span className="font-medium">{s.name}</span>
                      <span className="text-text-muted font-mono">{s.tco}</span>
                      <span className="text-text-muted">{s.dev}</span>
                      <span className={`text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded border ${s.statusColor}`}>{s.status}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="col-span-1 bg-surface border border-border rounded-lg p-5 shadow-sm flex flex-col">
                <h3 className="text-sm font-semibold mb-3 text-text-primary flex items-center gap-2">
                  <BrainCircuit size={16} className="text-ai" />
                  AI Recommendation
                </h3>
                <p className="text-xs text-text-muted mb-4 leading-relaxed flex-1">
                  TechCorp is recommended based on the best total cost, 100% compliance with corporate policy, and a clean supplier history.
                </p>
                <div className="space-y-2 mt-auto">
                  <div className="flex items-center gap-2 text-xs text-success">
                    <CheckCircle size={14} /> <span>Within budget</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-success">
                    <CheckCircle size={14} /> <span>Meets delivery SLA</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Integration Band ──────────────────────────────────────────── */}
        <div className="w-full max-w-5xl mx-auto mb-32 border-y border-border py-8 text-center bg-surface/30">
          <p className="text-xs font-semibold text-text-muted uppercase tracking-widest mb-6">Designed to integrate seamlessly with</p>
          <div className="flex flex-wrap justify-center gap-12 text-text-muted/60 grayscale opacity-70">
            {/* Fake logos using typography */}
            <span className="text-xl font-bold tracking-tighter">SAP Ariba</span>
            <span className="text-xl font-black italic">ORACLE</span>
            <span className="text-xl font-semibold tracking-wide">workday.</span>
            <span className="text-xl font-bold tracking-tight">Microsoft Dynamics</span>
          </div>
        </div>

        {/* ── Workflow Steps ────────────────────────────────────────────── */}
        <div className="w-full max-w-6xl mx-auto mb-20 px-4">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-semibold tracking-tight mb-4">A deterministic engine for procurement</h2>
            <p className="text-text-muted text-sm max-w-2xl mx-auto">ProcureOps separates hard math from AI reasoning, ensuring every decision is auditable, exact, and strictly compliant with your policies.</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {WORKFLOW_STEPS.map((step, idx) => {
              const Icon = step.icon;
              const isAI = step.title === "AI Analysis";
              
              return (
                <div key={idx} className="group bg-surface hover:bg-surface-elevated border border-border hover:border-primary/50 p-6 rounded-xl transition-all shadow-sm hover:shadow-md cursor-default">
                  <div className={`
                    h-12 w-12 rounded-lg flex items-center justify-center mb-5 transition-colors
                    ${isAI 
                      ? 'bg-ai/10 text-ai group-hover:bg-ai/20' 
                      : 'bg-bg text-text-muted group-hover:text-primary'}
                  `}>
                    <Icon size={24} strokeWidth={1.5} />
                  </div>
                  <h3 className={`text-base font-semibold mb-2 ${isAI ? 'text-ai' : 'text-text-primary'}`}>
                    {step.title}
                  </h3>
                  <p className="text-sm text-text-muted leading-relaxed">
                    {step.description}
                  </p>
                </div>
              )
            })}
          </div>
        </div>

      </main>
      
      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t border-border py-8 bg-surface">
        <div className="max-w-7xl mx-auto px-8 flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-text-muted">
          <div className="flex items-center gap-2">
            <div className="h-5 w-5 rounded bg-primary/20 flex items-center justify-center text-primary font-bold">P</div>
            <span>© 2026 ProcureOps AI. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#" className="hover:text-primary transition-colors">Privacy Policy</a>
            <a href="#" className="hover:text-primary transition-colors">Terms of Service</a>
            <a href="#" className="hover:text-primary transition-colors">Documentation</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
