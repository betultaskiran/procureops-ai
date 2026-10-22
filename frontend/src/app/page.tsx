"use client";

import React from "react";
import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageToggle } from "@/components/language-toggle";
import { ProcureOpsLogo } from "@/components/brand/ProcureOpsLogo";
import { useTranslation } from "@/lib/i18n/I18nContext";
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
  Search
} from "lucide-react";

export default function LandingPage() {
  const { t } = useTranslation();

  const workflowSteps = [
    { step: 1, title: t("landing.workflow.step1_title"), desc: t("landing.workflow.step1_desc"), icon: FileText },
    { step: 2, title: t("landing.workflow.step2_title"), desc: t("landing.workflow.step2_desc"), icon: ScanText },
    { step: 3, title: t("landing.workflow.step3_title"), desc: t("landing.workflow.step3_desc"), icon: Calculator },
    { step: 4, title: t("landing.workflow.step4_title"), desc: t("landing.workflow.step4_desc"), icon: ShieldCheck },
    { step: 5, title: t("landing.workflow.step5_title"), desc: t("landing.workflow.step5_desc"), icon: BrainCircuit },
    { step: 6, title: t("landing.workflow.step6_title"), desc: t("landing.workflow.step6_desc"), icon: CheckCircle },
    { step: 7, title: t("landing.workflow.step7_title"), desc: t("landing.workflow.step7_desc"), icon: UserCheck },
    { step: 8, title: t("landing.workflow.step8_title"), desc: t("landing.workflow.step8_desc"), icon: ClipboardCheck },
  ];

  return (
    <div className="min-h-screen bg-bg text-text-primary flex flex-col font-sans">
      {/* ── Navbar ──────────────────────────────────────────────────────── */}
      <header className="border-b border-border px-8 py-4 sticky top-0 bg-bg/90 backdrop-blur-md z-50">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <ProcureOpsLogo size={36} />
            <span className="font-bold tracking-tight text-xl text-text-primary">
              ProcureOps
            </span>
            <span className="bg-gradient-to-r from-cyan-500 to-emerald-500 text-white font-bold text-xs px-2 py-0.5 rounded-md tracking-wider uppercase shadow-sm shadow-cyan-500/25">
              AI
            </span>
          </div>
          
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-text-muted">
            <Link href="#features" className="hover:text-primary transition-colors">
              {t("landing.nav.features")}
            </Link>
            <Link href="#workflow" className="hover:text-primary transition-colors">
              {t("landing.nav.workflow")}
            </Link>
          </div>

          <div className="flex items-center gap-3">
            <LanguageToggle />
            <ThemeToggle />
            <Link 
              href="/login"
              className="text-text-muted hover:text-text-primary px-3 py-2 rounded font-medium transition-colors text-sm"
            >
              {t("landing.nav.login")}
            </Link>
            <Link 
              href="/dashboard"
              className="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded font-medium transition-colors text-sm shadow-sm"
            >
              {t("landing.nav.dashboard")}
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
                {t("landing.hero.title_prefix")} <br/>
                <span className="text-primary">{t("landing.hero.title_highlight")}</span> <br/>
                {t("landing.hero.title_suffix")}
              </h1>
              <p className="text-base lg:text-lg text-text-muted leading-relaxed mb-8 max-w-xl">
                {t("landing.hero.subtitle")}
              </p>
              
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-12">
                <Link 
                  href="/register"
                  className="flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-white px-6 py-3 rounded-xl text-sm font-semibold transition-all shadow-sm group w-full sm:w-auto"
                >
                  {t("landing.hero.start_free")}
                  <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </Link>
                
                <Link 
                  href="/login"
                  className="flex items-center justify-center gap-2 bg-surface border border-border hover:bg-surface-elevated text-text-primary px-6 py-3 rounded-xl text-sm font-semibold transition-all w-full sm:w-auto"
                >
                  {t("landing.hero.sign_in")}
                </Link>
              </div>

              {/* Technical Metrics */}
              <div className="flex flex-col sm:flex-row gap-6 sm:gap-0 border-y border-border py-6">
                <div className="flex-1 sm:pr-6 sm:border-r border-border">
                  <div className="font-semibold text-text-primary text-sm mb-1">{t("landing.metrics.deterministic_title")}</div>
                  <div className="text-text-muted text-[11px] leading-relaxed">{t("landing.metrics.deterministic_desc")}</div>
                </div>
                <div className="flex-1 sm:px-6 sm:border-r border-border">
                  <div className="font-semibold text-text-primary text-sm mb-1">{t("landing.metrics.auditable_title")}</div>
                  <div className="text-text-muted text-[11px] leading-relaxed">{t("landing.metrics.auditable_desc")}</div>
                </div>
                <div className="flex-1 sm:pl-6">
                  <div className="font-semibold text-text-primary text-sm mb-1">{t("landing.metrics.verified_title")}</div>
                  <div className="text-text-muted text-[11px] leading-relaxed">{t("landing.metrics.verified_desc")}</div>
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
                      <div className="font-semibold text-text-primary text-sm">{t("landing.flow.quotes_title")}</div>
                      <div className="text-xs text-text-muted">{t("landing.flow.quotes_desc")}</div>
                    </div>
                  </div>

                  {/* Node 2 */}
                  <div className="relative z-10 flex items-center gap-4 ml-8 transform hover:translate-x-2 transition-transform cursor-default">
                    <div className="w-12 h-12 rounded-full bg-bg border-2 border-ai/40 flex items-center justify-center text-ai shadow-sm shadow-ai/10 shrink-0">
                      <BrainCircuit size={20} />
                    </div>
                    <div>
                      <div className="font-semibold text-text-primary text-sm">{t("landing.flow.analysis_title")}</div>
                      <div className="text-xs text-text-muted">{t("landing.flow.analysis_desc")}</div>
                    </div>
                  </div>

                  {/* Node 3 */}
                  <div className="relative z-10 flex items-center gap-4 ml-16 transform hover:translate-x-2 transition-transform cursor-default">
                    <div className="w-12 h-12 rounded-full bg-bg border-2 border-primary/40 flex items-center justify-center text-primary shadow-sm shadow-primary/10 shrink-0">
                      <ShieldCheck size={20} />
                    </div>
                    <div>
                      <div className="font-semibold text-text-primary text-sm">{t("landing.flow.evidence_title")}</div>
                      <div className="text-xs text-text-muted">{t("landing.flow.evidence_desc")}</div>
                    </div>
                  </div>
                  
                  {/* Mini Decision Preview Card (Node 4) */}
                  <div className="relative z-20 w-full bg-surface-elevated border border-border rounded-xl shadow-xl shadow-black/5 p-5 mt-4 ml-20 transition-transform hover:-translate-y-1 duration-300">
                    <div className="flex items-center justify-between mb-4 pb-3 border-b border-border">
                      <div className="text-xs font-semibold text-text-muted uppercase tracking-wider">{t("landing.flow.decision_preview")}</div>
                      <UserCheck size={14} className="text-primary" />
                    </div>
                    
                    <div className="mb-4">
                      <div className="text-sm font-semibold text-text-primary mb-1">TechCorp</div>
                      <div className="flex gap-4 text-xs text-text-muted">
                        <span>407,200 TRY</span>
                        <span>•</span>
                        <span>{t("landing.flow.delivery_days", { days: 10 })}</span>
                      </div>
                    </div>

                    <div className="flex gap-2 mb-4">
                      <span className="inline-flex items-center gap-1 bg-success/10 text-success px-2 py-1 rounded text-[10px] font-semibold border border-success/20">
                        <Check size={10} /> {t("landing.flow.compliance_pass")}
                      </span>
                      <span className="inline-flex items-center gap-1 bg-primary/10 text-primary px-2 py-1 rounded text-[10px] font-semibold border border-primary/20">
                        {t("landing.flow.ai_recommended")}
                      </span>
                    </div>

                    <div className="bg-surface border border-border rounded p-3 text-xs flex gap-3 mb-3">
                      <FileText size={16} className="text-text-muted shrink-0 mt-0.5" />
                      <div>
                        <div className="font-medium text-text-primary mb-0.5">{t("landing.flow.evidence_verified")}</div>
                        <div className="text-text-muted text-[10px]">{t("landing.flow.evidence_detail", { id: 12 })}</div>
                      </div>
                    </div>

                    {/* Operational Output Badge */}
                    <div className="flex items-center gap-2 bg-text-primary/5 border border-border rounded px-3 py-2 text-[10px] font-medium text-text-primary">
                      <ClipboardCheck size={12} className="text-primary" />
                      {t("landing.flow.po_draft_ready")}
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
              <h2 className="text-3xl font-semibold tracking-tight text-text-primary mb-4">{t("landing.principles.title")}</h2>
              <p className="text-text-muted text-sm max-w-xl mx-auto">
                {t("landing.principles.subtitle")}
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-6">
              <div className="bg-surface-elevated border border-border p-8 rounded-xl hover:border-primary/50 transition-colors">
                <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mb-6">
                  <Search className="text-primary" size={24} />
                </div>
                <h3 className="text-lg font-semibold text-text-primary mb-3">{t("landing.principles.card1_title")}</h3>
                <p className="text-sm text-text-muted leading-relaxed mb-6">
                  {t("landing.principles.card1_desc")}
                </p>
              </div>

              <div className="bg-surface-elevated border border-border p-8 rounded-xl hover:border-primary/50 transition-colors">
                <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mb-6">
                  <Calculator className="text-primary" size={24} />
                </div>
                <h3 className="text-lg font-semibold text-text-primary mb-3">{t("landing.principles.card2_title")}</h3>
                <p className="text-sm text-text-muted leading-relaxed mb-6">
                  {t("landing.principles.card2_desc")}
                </p>
              </div>

              <div className="bg-surface-elevated border border-border p-8 rounded-xl hover:border-primary/50 transition-colors">
                <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mb-6">
                  <UserCheck className="text-primary" size={24} />
                </div>
                <h3 className="text-lg font-semibold text-text-primary mb-3">{t("landing.principles.card3_title")}</h3>
                <p className="text-sm text-text-muted leading-relaxed mb-6">
                  {t("landing.principles.card3_desc")}
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Procurement Workflow Stepper ──────────────────────────────── */}
        <section id="workflow" className="py-24 px-8 border-t border-border bg-bg">
          <div className="mx-auto max-w-7xl">
            <h2 className="text-2xl font-semibold tracking-tight text-text-primary mb-2">{t("landing.workflow.title")}</h2>
            <p className="text-text-muted text-sm mb-16">{t("landing.workflow.subtitle")}</p>

            <div className="relative flex flex-col md:flex-row items-start justify-between w-full">
              {/* Horizontal Line connecting steps */}
              <div className="hidden md:block absolute top-4 left-0 w-full h-[2px] bg-border z-0"></div>

              {workflowSteps.map((step, idx) => {
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
                {t("landing.cta.title")}
              </h2>
              <p className="text-slate-400 mb-10 max-w-2xl mx-auto text-sm md:text-base">
                {t("landing.cta.subtitle")}
              </p>
              
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-12">
                <Link 
                  href="/dashboard"
                  className="bg-primary hover:bg-primary-hover text-white px-8 py-3 rounded text-sm font-medium transition-all shadow-sm w-full sm:w-auto"
                >
                  {t("landing.cta.get_started")}
                </Link>
                <button 
                  className="bg-transparent border border-slate-700 hover:bg-slate-800 text-white px-8 py-3 rounded text-sm font-medium transition-all w-full sm:w-auto"
                >
                  {t("landing.cta.request_demo")}
                </button>
              </div>

              {/* Trust Checkpoints */}
              <div className="flex flex-col md:flex-row items-center justify-center gap-6 md:gap-12 pt-8 border-t border-slate-800/80">
                <div className="flex items-center gap-2 text-slate-300 text-xs font-medium">
                  <Check size={16} className="text-primary" />
                  {t("landing.cta.trust1")}
                </div>
                <div className="flex items-center gap-2 text-slate-300 text-xs font-medium">
                  <Check size={16} className="text-primary" />
                  {t("landing.cta.trust2")}
                </div>
              </div>
            </div>
          </div>
        </section>

      </main>
      
      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t border-border py-8 px-8 bg-surface">
        <div className="mx-auto max-w-7xl flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-text-muted">
          <div>{t("landing.footer.copyright")}</div>
          <div className="flex gap-6">
            <span className="hover:text-text-primary cursor-pointer transition-colors">{t("landing.footer.tag1")}</span>
            <span className="hover:text-text-primary cursor-pointer transition-colors">{t("landing.footer.tag2")}</span>
            <span className="hover:text-text-primary cursor-pointer transition-colors">{t("landing.footer.tag3")}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
