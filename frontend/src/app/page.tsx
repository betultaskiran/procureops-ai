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
  ArrowRight,
  ClipboardCheck,
  Check,
  Search,
  Play
} from "lucide-react";

export const metadata: Metadata = {
  title: "ProcureOps | Enterprise AI Procurement",
  description: "B2B AI-powered procurement decision and workflow platform.",
};

const WORKFLOW_STEPS = [
  { step: 1, title: "Quote Upload", desc: "PDF/Excel", icon: FileText },
  { step: 2, title: "Extraction", desc: "Structured data", icon: ScanText },
  { step: 3, title: "Calculation", desc: "TCO & VAT", icon: Calculator },
  { step: 4, title: "Compliance", desc: "Deterministic hard rules filter", icon: ShieldCheck },
  { step: 5, title: "AI Analysis", desc: "Recommendation", icon: BrainCircuit },
  { step: 6, title: "Verification", desc: "Deterministic audit & guardrail", icon: CheckCircle },
  { step: 7, title: "Approval", desc: "Human review", icon: UserCheck },
  { step: 8, title: "PO & Dispatch", desc: "Auto-generated PO & automated supplier email", icon: ClipboardCheck },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-bg text-text-primary flex flex-col font-sans">
      {/* ── Navbar ──────────────────────────────────────────────────────── */}
      <header className="border-b border-border px-8 py-4 sticky top-0 bg-bg/90 backdrop-blur-md z-50">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded bg-primary flex items-center justify-center text-white font-bold text-lg shadow-sm">
              P
            </div>
            <span className="font-semibold tracking-tight text-xl">ProcureOps</span>
          </div>
          
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-text-muted">
            <Link href="#features" className="hover:text-primary transition-colors">Features</Link>
            <Link href="#workflow" className="hover:text-primary transition-colors">How it Works</Link>
          </div>

          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link 
              href="/login"
              className="text-text-muted hover:text-text-primary px-3 py-2 rounded font-medium transition-colors text-sm"
            >
              Giriş Yap
            </Link>
            <Link 
              href="/dashboard"
              className="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded font-medium transition-colors text-sm shadow-sm"
            >
              Dashboard
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1 flex flex-col">
        
        {/* ── Hero Section ────────────────────────────────────────────────── */}
        <section className="relative overflow-hidden py-16 lg:py-20 px-8 border-b border-border">
          <div className="mx-auto max-w-7xl grid lg:grid-cols-[1.2fr_1fr] gap-12 lg:gap-16 items-center">
            
            {/* Left: Text Content */}
            <div className="max-w-2xl">
              <h1 className="text-4xl md:text-5xl lg:text-6xl font-semibold tracking-tight leading-[1.15] mb-6 text-text-primary">
                Turn supplier quotes into <br/>
                <span className="text-primary">confident procurement</span> <br/>
                decisions.
              </h1>
              <p className="text-base lg:text-lg text-text-muted leading-relaxed mb-8 max-w-xl">
                ProcureOps combines AI, policy intelligence and real-time data to help you 
                find the best suppliers, manage risks and streamline your procurement workflow.
              </p>
              
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-12">
                <Link 
                  href="/register"
                  className="flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-white px-6 py-3 rounded-xl text-sm font-semibold transition-all shadow-sm group w-full sm:w-auto"
                >
                  Ücretsiz Başla
                  <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </Link>
                
                <Link 
                  href="/login"
                  className="flex items-center justify-center gap-2 bg-surface border border-border hover:bg-surface-elevated text-text-primary px-6 py-3 rounded-xl text-sm font-semibold transition-all w-full sm:w-auto"
                >
                  Giriş Yap
                </Link>
              </div>

              {/* Technical Metrics */}
              <div className="flex flex-col sm:flex-row gap-6 sm:gap-0 border-y border-border py-6">
                <div className="flex-1 sm:pr-6 sm:border-r border-border">
                  <div className="font-semibold text-text-primary text-sm mb-1">Deterministic First</div>
                  <div className="text-text-muted text-[11px] leading-relaxed">Critical calculations don't rely on unpredictable LLM outputs.</div>
                </div>
                <div className="flex-1 sm:px-6 sm:border-r border-border">
                  <div className="font-semibold text-text-primary text-sm mb-1">Auditable Math</div>
                  <div className="text-text-muted text-[11px] leading-relaxed">TCO and VAT calculations are deterministic and traceable.</div>
                </div>
                <div className="flex-1 sm:pl-6">
                  <div className="font-semibold text-text-primary text-sm mb-1">Verified Recommendations</div>
                  <div className="text-text-muted text-[11px] leading-relaxed">AI outputs are strictly checked against rules and evidence.</div>
                </div>
              </div>
            </div>

            {/* Right: Abstract UI Graphic + Mini Preview Card */}
            <div className="relative hidden lg:flex justify-center items-center h-full pt-4">
              
              <div className="relative z-10 w-full flex flex-col items-center">
                
                <div className="relative flex flex-col gap-6 w-full max-w-[340px]">
                  
                  {/* Connecting Curved Lines */}
                  <svg className="absolute w-full h-[120%] left-[24px] top-[24px]" style={{ zIndex: 0, pointerEvents: 'none' }}>
                    <path 
                      d="M 0,0 C 0,36 32,36 32,72 C 32,108 64,108 64,144 C 64,190 186,180 186,230" 
                      fill="none" 
                      stroke="currentColor" 
                      strokeWidth="2" 
                      className="text-border" 
                      strokeDasharray="5 5"
                    />
                  </svg>

                  {/* Node 1 */}
                  <div className="relative z-10 flex items-center gap-4 ml-0 transform hover:translate-x-2 transition-transform cursor-default">
                    <div className="w-12 h-12 rounded-full bg-bg border-2 border-border flex items-center justify-center text-text-muted shadow-sm shrink-0">
                      <FileText size={20} />
                    </div>
                    <div>
                      <div className="font-semibold text-text-primary text-sm">Supplier Quotes</div>
                      <div className="text-xs text-text-muted">Upload & receive</div>
                    </div>
                  </div>

                  {/* Node 2 */}
                  <div className="relative z-10 flex items-center gap-4 ml-8 transform hover:translate-x-2 transition-transform cursor-default">
                    <div className="w-12 h-12 rounded-full bg-bg border-2 border-ai/40 flex items-center justify-center text-ai shadow-sm shadow-ai/10 shrink-0">
                      <BrainCircuit size={20} />
                    </div>
                    <div>
                      <div className="font-semibold text-text-primary text-sm">AI Analysis</div>
                      <div className="text-xs text-text-muted">Evaluate risk & TCO</div>
                    </div>
                  </div>

                  {/* Node 3 */}
                  <div className="relative z-10 flex items-center gap-4 ml-16 transform hover:translate-x-2 transition-transform cursor-default">
                    <div className="w-12 h-12 rounded-full bg-bg border-2 border-primary/40 flex items-center justify-center text-primary shadow-sm shadow-primary/10 shrink-0">
                      <ShieldCheck size={20} />
                    </div>
                    <div>
                      <div className="font-semibold text-text-primary text-sm">Evidence</div>
                      <div className="text-xs text-text-muted">Verify sources</div>
                    </div>
                  </div>
                  
                  {/* Mini Decision Preview Card (Node 4) */}
                  <div className="relative z-20 w-full bg-surface-elevated border border-border rounded-xl shadow-xl shadow-black/5 p-5 mt-4 ml-20 transition-transform hover:-translate-y-1 duration-300">
                    <div className="flex items-center justify-between mb-4 pb-3 border-b border-border">
                      <div className="text-xs font-semibold text-text-muted uppercase tracking-wider">Decision Preview</div>
                      <UserCheck size={14} className="text-primary" />
                    </div>
                    
                    <div className="mb-4">
                      <div className="text-sm font-semibold text-text-primary mb-1">TechCorp</div>
                      <div className="flex gap-4 text-xs text-text-muted">
                        <span>407,200 TRY</span>
                        <span>•</span>
                        <span>Delivery: 10 days</span>
                      </div>
                    </div>

                    <div className="flex gap-2 mb-4">
                      <span className="inline-flex items-center gap-1 bg-success/10 text-success px-2 py-1 rounded text-[10px] font-semibold border border-success/20">
                        <Check size={10} /> Compliance: PASS
                      </span>
                      <span className="inline-flex items-center gap-1 bg-primary/10 text-primary px-2 py-1 rounded text-[10px] font-semibold border border-primary/20">
                        AI: RECOMMENDED
                      </span>
                    </div>

                    <div className="bg-surface border border-border rounded p-3 text-xs flex gap-3 mb-3">
                      <FileText size={16} className="text-text-muted shrink-0 mt-0.5" />
                      <div>
                        <div className="font-medium text-text-primary mb-0.5">Evidence Verified</div>
                        <div className="text-text-muted text-[10px]">Policy #12 & TCO Formula Checked</div>
                      </div>
                    </div>

                    {/* Operational Output Badge */}
                    <div className="flex items-center gap-2 bg-text-primary/5 border border-border rounded px-3 py-2 text-[10px] font-medium text-text-primary">
                      <ClipboardCheck size={12} className="text-primary" />
                      PO Draft: Ready (Auto-email configured)
                    </div>
                  </div>

                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Principles / Features Section ──────────────────────────────── */}
        <section id="features" className="py-24 px-8 bg-surface">
          <div className="mx-auto max-w-7xl">
            <div className="text-center mb-16">
              <h2 className="text-3xl font-semibold tracking-tight text-text-primary mb-4">Built on the right principles</h2>
              <p className="text-text-muted text-sm max-w-xl mx-auto">
                LLMs interpret and orchestrate. Deterministic systems calculate and verify. 
                We combine both to build a trustworthy enterprise engine.
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-6">
              <div className="bg-surface-elevated border border-border p-8 rounded-xl hover:border-primary/50 transition-colors">
                <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mb-6">
                  <Search className="text-primary" size={24} />
                </div>
                <h3 className="text-lg font-semibold text-text-primary mb-3">Evidence-Backed Decisions</h3>
                <p className="text-sm text-text-muted leading-relaxed mb-6">
                  Every recommendation is grounded in citations from policy documents, 
                  supplier history, and structured quote data. No hallucinated claims.
                </p>
              </div>

              <div className="bg-surface-elevated border border-border p-8 rounded-xl hover:border-primary/50 transition-colors">
                <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mb-6">
                  <Calculator className="text-primary" size={24} />
                </div>
                <h3 className="text-lg font-semibold text-text-primary mb-3">Deterministic Calculations</h3>
                <p className="text-sm text-text-muted leading-relaxed mb-6">
                  TCO, VAT, and discount calculations are performed by strict backend code — 
                  not the LLM. Results are exact, auditable, and reliable.
                </p>
              </div>

              <div className="bg-surface-elevated border border-border p-8 rounded-xl hover:border-primary/50 transition-colors">
                <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mb-6">
                  <UserCheck className="text-primary" size={24} />
                </div>
                <h3 className="text-lg font-semibold text-text-primary mb-3">Human in the Loop</h3>
                <p className="text-sm text-text-muted leading-relaxed mb-6">
                  AI prepares and explains. Humans decide. Managers can approve, reject, 
                  or request revisions with full contextual awareness.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Procurement Workflow Stepper ──────────────────────────────── */}
        <section id="workflow" className="py-24 px-8 border-t border-border bg-bg">
          <div className="mx-auto max-w-7xl">
            <h2 className="text-2xl font-semibold tracking-tight text-text-primary mb-2">Procurement Workflow</h2>
            <p className="text-text-muted text-sm mb-16">From quote to purchase order, all in one place.</p>

            <div className="relative flex flex-col md:flex-row items-start justify-between w-full">
              {/* Horizontal Line connecting steps */}
              <div className="hidden md:block absolute top-4 left-0 w-full h-[2px] bg-border z-0"></div>

              {WORKFLOW_STEPS.map((step, idx) => {
                return (
                  <div key={idx} className="relative z-10 flex flex-row md:flex-col items-center md:items-center gap-4 md:gap-3 w-full md:w-auto mb-8 md:mb-0 group cursor-pointer">
                    
                    {/* Solid background wrapper to hide the line underneath */}
                    <div className="relative w-8 h-8 rounded-full bg-bg z-10">
                      <div className="
                        w-full h-full rounded-full flex items-center justify-center text-xs font-bold border transition-all duration-300
                        bg-primary/10 border-primary/40 text-primary shadow-sm
                        group-hover:bg-primary group-hover:border-primary group-hover:text-white group-hover:scale-110 group-hover:shadow-md
                      ">
                        <step.icon size={14} strokeWidth={2.5} />
                      </div>
                    </div>
                    
                    <div className="text-left md:text-center mt-0 md:mt-2 transition-transform duration-300 group-hover:-translate-y-0.5">
                      <div className="text-xs font-semibold text-text-primary whitespace-nowrap">{step.step}. {step.title}</div>
                      <div className="text-[10px] text-text-muted mt-1 whitespace-nowrap">{step.desc}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Final CTA Section ──────────────────────────────────────────── */}
        <section className="py-24 px-8 bg-surface-elevated border-t border-border">
          <div className="mx-auto max-w-5xl bg-slate-900 rounded-2xl p-12 md:p-16 border border-slate-800 shadow-2xl relative overflow-hidden text-center">
            
            {/* Subtle background glow */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/4 h-32 bg-primary/20 blur-[100px] rounded-full pointer-events-none"></div>

            <div className="relative z-10">
              <h2 className="text-3xl md:text-4xl font-semibold tracking-tight text-white mb-6">
                Ready to automate complex procurement decisions?
              </h2>
              <p className="text-slate-400 mb-10 max-w-2xl mx-auto text-sm md:text-base">
                Join leading enterprise teams using ProcureOps to ensure deterministic accuracy, 
                evidence-backed AI recommendations, and strict policy compliance.
              </p>
              
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-12">
                <Link 
                  href="/dashboard"
                  className="bg-primary hover:bg-primary-hover text-white px-8 py-3 rounded text-sm font-medium transition-all shadow-sm w-full sm:w-auto"
                >
                  Get Started
                </Link>
                <button 
                  className="bg-transparent border border-slate-700 hover:bg-slate-800 text-white px-8 py-3 rounded text-sm font-medium transition-all w-full sm:w-auto"
                >
                  Request Demo
                </button>
              </div>

              {/* Trust Checkpoints */}
              <div className="flex flex-col md:flex-row items-center justify-center gap-6 md:gap-12 pt-8 border-t border-slate-800/80">
                <div className="flex items-center gap-2 text-slate-300 text-xs font-medium">
                  <Check size={16} className="text-primary" />
                  SOC2 Type II & Enterprise Audit Ready
                </div>
                <div className="flex items-center gap-2 text-slate-300 text-xs font-medium">
                  <Check size={16} className="text-primary" />
                  Zero Data Retention for LLM Training
                </div>
              </div>
            </div>
          </div>
        </section>

      </main>
      
      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t border-border py-8 px-8 bg-surface">
        <div className="mx-auto max-w-7xl flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-text-muted">
          <div>© 2026 ProcureOps AI. All rights reserved.</div>
          <div className="flex gap-6">
            <span className="hover:text-text-primary cursor-pointer transition-colors">Enterprise Grade</span>
            <span className="hover:text-text-primary cursor-pointer transition-colors">Deterministic AI</span>
            <span className="hover:text-text-primary cursor-pointer transition-colors">Audit-Ready</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
