import type { Metadata } from "next";
import { ThemeToggle } from "@/components/theme-toggle";
import Link from "next/link";
import { HeroSection } from "@/components/landing/HeroSection";
import { WorkflowPipeline } from "@/components/landing/WorkflowPipeline";

export const metadata: Metadata = {
  title: "ProcureOps | Enterprise AI Procurement",
  description: "B2B AI-powered procurement decision and workflow platform.",
};

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-bg text-text-primary flex flex-col font-sans selection:bg-primary/20">
      
      {/* ── Navbar ──────────────────────────────────────────────────────── */}
      <header className="border-b border-border px-6 py-4 sticky top-0 bg-bg/80 backdrop-blur-md z-50">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded bg-primary flex items-center justify-center text-white font-bold text-lg shadow-sm">
              P
            </div>
            <span className="font-semibold tracking-tight text-xl">ProcureOps</span>
          </div>
          
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-text-muted">
            <Link href="/dashboard" className="hover:text-primary transition-colors">Product</Link>
            <Link href="/rfqs" className="hover:text-primary transition-colors">Pipeline</Link>
            <Link href="/policies" className="hover:text-primary transition-colors">Architecture</Link>
          </nav>
          
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <Link 
              href="/dashboard"
              className="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-md font-medium transition-all shadow-sm text-sm"
            >
              Go to App
            </Link>
          </div>
        </div>
      </header>

      {/* ── Main Content ────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col items-center w-full relative">
        
        {/* Subtle Grid Background for Hero */}
        <div className="absolute top-0 inset-x-0 h-[600px] bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] pointer-events-none -z-10" />

        <HeroSection />
        
        {/* Divider */}
        <div className="w-full max-w-5xl mx-auto h-px bg-gradient-to-r from-transparent via-border to-transparent my-4" />
        
        <WorkflowPipeline />
        
      </main>

    </div>
  );
}
