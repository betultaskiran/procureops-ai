"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { 
  Lock, 
  Mail, 
  Eye, 
  EyeOff, 
  ArrowRight, 
  AlertCircle, 
  Loader2,
  Building2
} from "lucide-react";
import { useAuth } from "@/lib/auth/AuthContext";
import { ApiError } from "@/lib/api/client";
import { useTranslation } from "@/lib/i18n/I18nContext";
import { getLocalizedApiError } from "@/lib/i18n/apiErrorMap";
import { LanguageToggle } from "@/components/language-toggle";
import { ThemeToggle } from "@/components/theme-toggle";
import { ProcureOpsLogo } from "@/components/brand/ProcureOpsLogo";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const { t, locale } = useTranslation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If already authenticated, redirect to target or dashboard
  useEffect(() => {
    if (!isAuthLoading && isAuthenticated) {
      const redirect = searchParams.get("redirect") || "/dashboard";
      router.replace(redirect);
    }
  }, [isAuthenticated, isAuthLoading, router, searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const cleanEmail = email.trim();
    if (!cleanEmail || !password) {
      setError(t("auth.login.empty_fields_error"));
      return;
    }

    try {
      setIsSubmitting(true);
      await login({
        email: cleanEmail,
        password,
      });

      const redirect = searchParams.get("redirect") || "/dashboard";
      router.push(redirect);
    } catch (err: any) {
      setError(getLocalizedApiError(err, locale));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg flex flex-col justify-center items-center p-4 sm:p-6 font-sans relative">
      {/* ── Public Controls Header ───────────────────────────────────────── */}
      <div className="absolute top-4 right-4 flex items-center gap-2 z-10">
        <LanguageToggle />
        <ThemeToggle />
      </div>

      {/* ── Brand Logo Header ────────────────────────────────────────────── */}
      <div className="mb-8 text-center">
        <Link href="/" className="inline-flex items-center gap-3 group">
          <ProcureOpsLogo size={46} className="group-hover:scale-105 transition-transform" />
          <span className="font-bold tracking-tight text-2xl text-text-primary">
            ProcureOps
          </span>
          <span className="bg-gradient-to-r from-cyan-500 to-emerald-500 text-white font-bold text-xs px-2 py-0.5 rounded-md tracking-wider uppercase shadow-md shadow-cyan-500/25">
            AI
          </span>
        </Link>
        <p className="text-xs text-text-muted mt-2">
          {t("auth.login.brand_subtitle")}
        </p>
      </div>

      {/* ── Login Card ───────────────────────────────────────────────────── */}
      <div className="w-full max-w-md bg-surface border border-border rounded-2xl shadow-xl overflow-hidden p-6 sm:p-8">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-text-primary tracking-tight">
            {t("auth.login.card_title")}
          </h1>
          <p className="text-xs text-text-muted mt-1">
            {t("auth.login.card_subtitle")}
          </p>
        </div>

        {error && (
          <div className="mb-5 p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 text-xs flex items-start gap-2.5 animate-in fade-in duration-200">
            <AlertCircle size={16} className="shrink-0 mt-0.5" />
            <div className="leading-relaxed">{error}</div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1.5">
              {t("auth.login.email_label")}
            </label>
            <div className="relative">
              <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="email"
                required
                autoComplete="email"
                placeholder={t("auth.login.email_placeholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 text-sm bg-surface-elevated border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold text-text-primary">
                {t("auth.login.password_label")}
              </label>
            </div>
            <div className="relative">
              <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type={showPassword ? "text" : "password"}
                required
                autoComplete="current-password"
                placeholder={t("auth.login.password_placeholder")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-11 py-2.5 text-sm bg-surface-elevated border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
                title={showPassword ? t("auth.login.hide_password") : t("auth.login.show_password")}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full mt-2 py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-white text-sm font-semibold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                <span>{t("auth.login.submitting")}</span>
              </>
            ) : (
              <>
                <span>{t("auth.login.submit")}</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        <div className="mt-6 pt-6 border-t border-border text-center space-y-3">
          <p className="text-xs text-text-muted">
            {t("auth.login.new_company_prompt")}{" "}
            <Link 
              href="/register" 
              className="text-primary hover:underline font-semibold"
            >
              {t("auth.login.register_link")}
            </Link>
          </p>
          <p className="text-[11px] text-text-muted/80">
            {t("auth.login.existing_org_hint")}
          </p>
        </div>
      </div>

      <div className="mt-8 text-center text-xs text-text-muted">
        <Link href="/" className="hover:text-text-primary transition-colors">
          {t("auth.login.return_home")}
        </Link>
      </div>

    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <Loader2 size={28} className="animate-spin text-primary" />
      </div>
    }>
      <LoginForm />
    </Suspense>
  );
}
