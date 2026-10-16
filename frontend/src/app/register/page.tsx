"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { 
  Building2, 
  User, 
  Mail, 
  Lock, 
  Eye, 
  EyeOff, 
  ArrowRight, 
  AlertCircle, 
  Loader2,
  ShieldCheck,
  Info
} from "lucide-react";
import { useAuth } from "@/lib/auth/AuthContext";
import { ApiError } from "@/lib/api/client";

function RegisterForm() {
  const router = useRouter();
  const { register, isAuthenticated, isLoading: isAuthLoading } = useAuth();

  const [companyName, setCompanyName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If already authenticated, redirect to dashboard
  useEffect(() => {
    if (!isAuthLoading && isAuthenticated) {
      router.replace("/dashboard");
    }
  }, [isAuthenticated, isAuthLoading, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const cleanCompany = companyName.trim();
    const cleanName = fullName.trim();
    const cleanEmail = email.trim().toLowerCase();

    if (cleanCompany.length < 2) {
      setError("Şirket adı en az 2 karakter olmalıdır.");
      return;
    }

    if (cleanName.length < 2) {
      setError("Ad Soyad en az 2 karakter olmalıdır.");
      return;
    }

    if (password.length < 8) {
      setError("Şifre en az 8 karakter uzunluğunda olmalıdır.");
      return;
    }

    try {
      setIsSubmitting(true);
      await register({
        company_name: cleanCompany,
        full_name: cleanName,
        email: cleanEmail,
        password,
      });

      router.push("/dashboard");
    } catch (err: any) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          if (err.message?.toLowerCase().includes("email")) {
            setError("Bu e-posta adresiyle kayıtlı bir kullanıcı zaten mevcut.");
          } else if (err.message?.toLowerCase().includes("organization") || err.message?.toLowerCase().includes("slug")) {
            setError("Bu isimde bir organizasyon zaten mevcut. Lütfen farklı bir şirket adı deneyin.");
          } else {
            setError(err.message || "Kayıt çakışması: Bu bilgilerle bir hesap zaten mevcut.");
          }
        } else if (err.status === 422) {
          setError("Girdiğiniz bilgileri lütfen kontrol edin (şifre en az 8 karakter olmalıdır).");
        } else {
          setError(err.message || "Kayıt işlemi sırasında bir hata oluştu.");
        }
      } else {
        setError("Sunucuya bağlanırken bir sorun oluştu. Lütfen bağlantınızı kontrol edin.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg flex flex-col justify-center items-center p-4 sm:p-6 font-sans">
      
      {/* ── Brand Logo Header ────────────────────────────────────────────── */}
      <div className="mb-8 text-center">
        <Link href="/" className="inline-flex items-center gap-3 group">
          <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center text-white font-bold text-xl shadow-md group-hover:scale-105 transition-transform">
            P
          </div>
          <span className="font-bold tracking-tight text-2xl text-text-primary">
            ProcureOps <span className="text-primary font-normal">AI</span>
          </span>
        </Link>
        <p className="text-xs text-text-muted mt-2">
          Yeni Organizasyon & İlk Yönetici Kaydı
        </p>
      </div>

      {/* ── Registration Card ────────────────────────────────────────────── */}
      <div className="w-full max-w-lg bg-surface border border-border rounded-2xl shadow-xl overflow-hidden p-6 sm:p-8">
        <div className="mb-5">
          <h1 className="text-xl font-bold text-text-primary tracking-tight">
            Şirketinizi Kaydedin
          </h1>
          <p className="text-xs text-text-muted mt-1">
            Şirketiniz adına bir çalışma alanı oluşturun ve kurucu yönetici (Admin) olarak başlayın.
          </p>
        </div>

        {/* Informational Scope Badge */}
        <div className="mb-5 p-3 rounded-xl bg-primary/10 border border-primary/20 text-text-primary text-xs flex items-start gap-2.5">
          <Info size={16} className="text-primary shrink-0 mt-0.5" />
          <div className="text-[11px] leading-relaxed text-text-muted">
            <strong className="text-text-primary">Önemli Not:</strong> Bu form yalnızca yeni bir şirket / organizasyon kurmak içindir. 
            Mevcut bir şirketin ekibine dahil olmak istiyorsanız, şirket yöneticinizden <strong>Ekip Yönetimi</strong> üzerinden davet talep ediniz.
          </div>
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
              Şirket / Organizasyon Adı
            </label>
            <div className="relative">
              <Building2 size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                required
                placeholder="Örn: Anadolu Endüstri A.Ş."
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 text-sm bg-surface-elevated border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1.5">
              Yönetici Ad Soyad
            </label>
            <div className="relative">
              <User size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                required
                placeholder="Örn: Mehmet Özkan"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 text-sm bg-surface-elevated border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1.5">
              Kurumsal E-posta
            </label>
            <div className="relative">
              <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="email"
                required
                autoComplete="email"
                placeholder="mehmet@sirketiniz.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 text-sm bg-surface-elevated border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold text-text-primary">
                Yönetici Şifresi
              </label>
              <span className="text-[10px] text-text-muted">En az 8 karakter</span>
            </div>
            <div className="relative">
              <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type={showPassword ? "text" : "password"}
                required
                minLength={8}
                autoComplete="new-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-11 py-2.5 text-sm bg-surface-elevated border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary transition-colors"
                title={showPassword ? "Şifreyi gizle" : "Şifreyi göster"}
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
                <span>Hesap Oluşturuluyor...</span>
              </>
            ) : (
              <>
                <span>Organizasyonu Kaydet ve Başla</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        <div className="mt-6 pt-6 border-t border-border text-center">
          <p className="text-xs text-text-muted">
            Zaten bir hesabınız var mı?{" "}
            <Link 
              href="/login" 
              className="text-primary hover:underline font-semibold"
            >
              Giriş Yapın
            </Link>
          </p>
        </div>
      </div>

      <div className="mt-8 text-center text-xs text-text-muted">
        <Link href="/" className="hover:text-text-primary transition-colors">
          ← Ana Sayfaya Dön
        </Link>
      </div>

    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <Loader2 size={28} className="animate-spin text-primary" />
      </div>
    }>
      <RegisterForm />
    </Suspense>
  );
}
