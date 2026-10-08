import Link from "next/link";
import { ArrowRight, PlayCircle } from "lucide-react";

export function HeroSection() {
  return (
    <section className="w-full max-w-7xl mx-auto px-6 pt-16 pb-12 flex flex-col items-center text-center relative z-10">
      <h1 className="text-4xl md:text-6xl font-semibold tracking-tight leading-[1.1] mb-6 text-text-primary max-w-4xl">
        Procurement decisions driven by <br className="hidden md:block" />
        <span className="text-primary">deterministic logic & AI.</span>
      </h1>
      
      <p className="text-base md:text-lg text-text-muted leading-relaxed max-w-2xl mb-10">
        ProcureOps eliminates hallucination by combining exact TCO calculations and hard policy rules with AI-driven reasoning. Every decision is verified, cited, and awaits your approval.
      </p>
      
      <div className="flex flex-col sm:flex-row items-center gap-4">
        <Link 
          href="/dashboard"
          className="flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-white px-6 py-3 rounded-md font-medium transition-all shadow-sm w-full sm:w-auto"
        >
          Enter Dashboard
          <ArrowRight size={18} />
        </Link>
        <button className="flex items-center justify-center gap-2 bg-surface border border-border hover:border-text-muted text-text-primary px-6 py-3 rounded-md font-medium transition-all shadow-sm w-full sm:w-auto group">
          <PlayCircle size={18} className="text-text-muted group-hover:text-primary transition-colors" />
          How it Works
        </button>
      </div>
    </section>
  );
}
