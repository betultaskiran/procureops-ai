"use client";

import React from "react";
import { AlertTriangle, RefreshCw, Loader2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/I18nContext";

interface StaleNoticeBannerProps {
  isStale: boolean;
  isAnalyzing: boolean;
  onRerunAnalysis: () => void;
  hasActivePo?: boolean;
  poNumber?: string | null;
}

export const StaleNoticeBanner: React.FC<StaleNoticeBannerProps> = ({
  isStale,
  isAnalyzing,
  onRerunAnalysis,
  hasActivePo = false,
  poNumber = null,
}) => {
  const { t } = useTranslation();

  if (!isStale) return null;

  return (
    <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm animate-in fade-in duration-200">
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-amber-300 block text-sm mb-0.5">
            {t("analysis.stale.title")}
          </span>
          <p className="text-text-muted leading-relaxed">
            {t("analysis.stale.desc")} {poNumber ? `(${poNumber})` : ""}
          </p>
        </div>
      </div>

      <button
        onClick={onRerunAnalysis}
        disabled={isAnalyzing}
        className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold text-xs transition-colors shrink-0 disabled:opacity-50 shadow-sm"
      >
        {isAnalyzing ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            <span>{t("analysis.stale.recalculating")}</span>
          </>
        ) : (
          <>
            <RefreshCw size={14} />
            <span>{t("analysis.stale.recalculate_btn")}</span>
          </>
        )}
      </button>
    </div>
  );
};
