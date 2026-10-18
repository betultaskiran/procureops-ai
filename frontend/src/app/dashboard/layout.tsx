"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { 
  LayoutDashboard, 
  FileText, 
  ShieldCheck, 
  Settings, 
  Users,
  LogOut,
  Building2,
  Loader2,
  Shield,
  CheckSquare
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/lib/auth/AuthContext";
import { UserRole } from "@/lib/api/types";

const ROLE_BADGES: Record<UserRole, { label: string; badgeClass: string }> = {
  admin: {
    label: "Admin",
    badgeClass: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20",
  },
  manager: {
    label: "Manager",
    badgeClass: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
  },
  purchasing_director: {
    label: "Satın Alma Direktörü",
    badgeClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  },
  cfo: {
    label: "CFO",
    badgeClass: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20",
  },
  employee: {
    label: "Uzman",
    badgeClass: "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20",
  },
  viewer: {
    label: "Gözlemci",
    badgeClass: "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20",
  },
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading, isAuthenticated, logout } = useAuth();

  // Route protection guard: redirect unauthenticated users to /login
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const redirectUrl = pathname ? `/login?redirect=${encodeURIComponent(pathname)}` : "/login";
      router.replace(redirectUrl);
    }
  }, [isLoading, isAuthenticated, router, pathname]);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  // Prevent flash of protected UI or 401 API calls before session validation
  if (isLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-bg flex flex-col items-center justify-center gap-3 font-sans">
        <Loader2 size={32} className="animate-spin text-primary" />
        <p className="text-xs text-text-muted">Kullanıcı oturumu doğrulanıyor...</p>
      </div>
    );
  }

  const roleConfig = user?.role ? ROLE_BADGES[user.role] : null;

  return (
    <div className="min-h-screen bg-bg flex font-sans">
      
      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <aside className="w-64 border-r border-border bg-surface flex flex-col hidden md:flex sticky top-0 h-screen">
        
        {/* Brand Logo & Organization */}
        <div className="h-16 flex items-center px-6 border-b border-border justify-between">
          <Link href="/dashboard" className="flex items-center gap-3">
            <div className="h-8 w-8 rounded bg-primary flex items-center justify-center text-white font-bold text-lg shadow-sm">
              P
            </div>
            <span className="font-semibold tracking-tight text-lg text-text-primary">ProcureOps</span>
          </Link>
        </div>

        {/* User Profile Summary Card */}
        {user && (
          <div className="p-4 border-b border-border bg-surface-elevated/40">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center text-sm shrink-0 border border-primary/20">
                {user.full_name?.charAt(0)?.toUpperCase() || "U"}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-1">
                  <span className="font-semibold text-xs text-text-primary truncate" title={user.full_name}>
                    {user.full_name}
                  </span>
                  {roleConfig && (
                    <span className={`text-[10px] px-1.5 py-0.2 rounded border font-medium shrink-0 ${roleConfig.badgeClass}`}>
                      {roleConfig.label}
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-text-muted truncate flex items-center gap-1 mt-0.5">
                  <Building2 size={11} className="shrink-0" />
                  <span className="truncate">{user.organization?.name || "Organizasyon"}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 py-4 px-4 flex flex-col gap-1 overflow-y-auto">
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

          <Link
            href="/dashboard/approvals"
            className={`flex items-center gap-3 px-3 py-2 rounded-md font-medium text-sm transition-colors ${
              pathname.startsWith("/dashboard/approvals")
                ? "bg-primary/10 text-primary"
                : "text-text-muted hover:bg-surface-elevated hover:text-text-primary"
            }`}
          >
            <CheckSquare size={18} />
            Approvals
          </Link>

          <Link
            href="/dashboard/team" 
            className={`flex items-center gap-3 px-3 py-2 rounded-md font-medium text-sm transition-colors ${
              pathname.startsWith("/dashboard/team")
                ? "bg-primary/10 text-primary" 
                : "text-text-muted hover:bg-surface-elevated hover:text-text-primary"
            }`}
          >
            <Users size={18} />
            Team
          </Link>
        </nav>

        {/* Footer Settings & Logout */}
        <div className="p-4 border-t border-border flex flex-col gap-1">
          <div className="flex items-center justify-between px-3 py-2 mb-2">
            <span className="text-sm font-medium text-text-muted">Theme</span>
            <ThemeToggle />
          </div>

          <button 
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2 rounded-md text-text-muted hover:bg-rose-500/10 hover:text-rose-600 dark:hover:text-rose-400 font-medium text-sm transition-colors w-full text-left"
          >
            <LogOut size={18} />
            <span>Oturumu Kapat</span>
          </button>
        </div>
      </aside>

      {/* ── Main Content Area ──────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0">
        
        {/* Mobile Header (Hidden on Desktop) */}
        <header className="h-16 border-b border-border bg-surface flex items-center justify-between px-6 md:hidden">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded bg-primary flex items-center justify-center text-white font-bold text-lg">P</div>
            <span className="font-semibold text-sm">{user?.organization?.name}</span>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <button 
              onClick={handleLogout} 
              className="p-2 text-text-muted hover:text-rose-500" 
              title="Çıkış Yap"
            >
              <LogOut size={18} />
            </button>
          </div>
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
