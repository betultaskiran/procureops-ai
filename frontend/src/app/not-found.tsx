"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/I18nContext";
import { LanguageToggle } from "@/components/language-toggle";
import { ThemeToggle } from "@/components/theme-toggle";

export default function NotFound() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-bg text-text-primary p-6 font-sans relative">
      <div className="absolute top-4 right-4 flex items-center gap-2">
        <LanguageToggle />
        <ThemeToggle />
      </div>

      <div className="text-center max-w-md bg-surface border border-border rounded-2xl shadow-xl p-8">
        <div className="h-12 w-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center mx-auto mb-4 font-bold text-xl">
          404
        </div>
        <h2 className="text-xl font-bold mb-2 tracking-tight">
          {t("not_found.title")}
        </h2>
        <p className="text-sm text-text-muted mb-6 leading-relaxed">
          {t("not_found.description")}
        </p>
        <Link
          href="/"
          className="inline-flex items-center justify-center px-4 py-2.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-sm font-semibold transition-all shadow-sm"
        >
          {t("not_found.return_home")}
        </Link>
      </div>
    </div>
  );
}
