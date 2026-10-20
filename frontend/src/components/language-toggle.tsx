"use client";

import React from "react";
import { Globe } from "lucide-react";
import { useTranslation } from "@/lib/i18n/I18nContext";

interface LanguageToggleProps {
  className?: string;
}

export function LanguageToggle({ className = "" }: LanguageToggleProps) {
  const { locale, setLocale } = useTranslation();

  const handleToggle = () => {
    const nextLocale = locale === "en" ? "tr" : "en";
    setLocale(nextLocale);
  };

  const titleText =
    locale === "en"
      ? "Türkçe'ye geç (Switch to Turkish)"
      : "Switch to English (İngilizce'ye geç)";

  return (
    <button
      onClick={handleToggle}
      type="button"
      className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium text-text-muted hover:bg-surface-elevated hover:text-text-primary border border-border/60 transition-colors ${className}`}
      title={titleText}
      aria-label={titleText}
    >
      <Globe className="h-3.5 w-3.5 text-text-muted" />
      <span className="font-semibold tracking-wider uppercase text-[11px] text-text-primary">
        {locale}
      </span>
    </button>
  );
}
