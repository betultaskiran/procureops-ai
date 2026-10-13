"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  LayoutDashboard, 
  FileText, 
  ShieldCheck, 
  Settings, 
  Users,
  LogOut
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen bg-bg flex font-sans">
      
      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <aside className="w-64 border-r border-border bg-surface flex flex-col hidden md:flex sticky top-0 h-screen">
        
        {/* Logo */}
        <div className="h-16 flex items-center px-6 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded bg-primary flex items-center justify-center text-white font-bold text-lg shadow-sm">
              P
            </div>
            <span className="font-semibold tracking-tight text-lg text-text-primary">ProcureOps</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-6 px-4 flex flex-col gap-1">
          <div className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2 px-3">
            Menu
          </div>
          
          <Link 
            href="/dashboard" 
            className={`flex items-center gap-3 px-3 py-2 rounded-md font-medium text-sm transition-colors ${
              pathname === "/dashboard" 
                ? "bg-primary/10 text-primary" 
                : "text-text-muted hover:bg-surface-elevated hover:text-text-primary"
            }`}
          >
            <LayoutDashboard size={18} />
            Dashboard
          </Link>
          
          <Link 
            href="/dashboard/quotes" 
            className={`flex items-center gap-3 px-3 py-2 rounded-md font-medium text-sm transition-colors ${
              pathname.startsWith("/dashboard/quotes")
                ? "bg-primary/10 text-primary" 
                : "text-text-muted hover:bg-surface-elevated hover:text-text-primary"
            }`}
          >
            <FileText size={18} />
            Quotes & RFQs
          </Link>
          
          <Link 
            href="/dashboard/policies" 
            className={`flex items-center gap-3 px-3 py-2 rounded-md font-medium text-sm transition-colors ${
              pathname.startsWith("/dashboard/policies")
                ? "bg-primary/10 text-primary" 
                : "text-text-muted hover:bg-surface-elevated hover:text-text-primary"
            }`}
          >
            <ShieldCheck size={18} />
            Policies
          </Link>

          <Link href="/dashboard/team" className="flex items-center gap-3 px-3 py-2 rounded-md text-text-muted hover:bg-surface-elevated hover:text-text-primary font-medium text-sm transition-colors">
            <Users size={18} />
            Team
          </Link>
        </nav>

        {/* Footer Settings */}
        <div className="p-4 border-t border-border flex flex-col gap-1">
          <div className="flex items-center justify-between px-3 py-2 mb-2">
            <span className="text-sm font-medium text-text-muted">Theme</span>
            <ThemeToggle />
          </div>

          <button className="flex items-center gap-3 px-3 py-2 rounded-md text-text-muted hover:bg-surface-elevated hover:text-text-primary font-medium text-sm transition-colors w-full text-left">
            <Settings size={18} />
            Settings
          </button>
          
          <button className="flex items-center gap-3 px-3 py-2 rounded-md text-text-muted hover:bg-red-500/10 hover:text-red-500 font-medium text-sm transition-colors w-full text-left mt-2">
            <LogOut size={18} />
            Log Out
          </button>
        </div>
      </aside>

      {/* ── Main Content Area ──────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0">
        
        {/* Mobile Header (Hidden on Desktop) */}
        <header className="h-16 border-b border-border bg-surface flex items-center justify-between px-6 md:hidden">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded bg-primary flex items-center justify-center text-white font-bold text-lg">P</div>
          </div>
          <ThemeToggle />
        </header>

        {/* Page Content */}
        <div className="flex-1 p-8 overflow-auto">
          <div className="max-w-6xl mx-auto">
            {children}
          </div>
        </div>
        
      </main>
    </div>
  );
}
