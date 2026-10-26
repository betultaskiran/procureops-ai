"use client";

import React, { useState, useEffect } from "react";
import { 
  Sparkles, 
  CheckCircle2, 
  Clock, 
  AlertTriangle, 
  RefreshCw, 
  ShieldCheck, 
  Database, 
  FileSearch, 
  Calculator,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import { StageResultResponse } from "@/lib/api/types";
import { useTranslation } from "@/lib/i18n";

interface AnalysisPipelineProgressProps {
  isAnalyzing: boolean;
  stageResults?: StageResultResponse[];
  verificationStatus?: string | null;
  error?: string | null;
  onRetry?: () => void;
  quoteCount?: number;
}

const STAGE_NAME_MAP: Record<string, { tr: string; en: string }> = {
  extraction_validation: {
    tr: "1. Belge ve Teklif Doğrulaması",
    en: "1. Document & Quote Validation",
  },
  deterministic_evaluation: {
    tr: "2. Deterministik TCO ve Kural Denetimi",
    en: "2. Deterministic TCO & Rule Evaluation",
  },
  policy_compliance: {
    tr: "3. Kurumsal Politika Taraması (Qdrant RAG)",
    en: "3. Corporate Policy Retrieval (Qdrant RAG)",
  },
  supplier_history: {
    tr: "Tedarikçi Geçmiş Performans Analizi",
    en: "Supplier Historical Performance Analysis",
  },
  supplier_recommendation: {
    tr: "4. Yapay Zeka Karar ve Trade-Off Analizi",
    en: "4. AI Decision & Trade-Off Analysis",
  },
  independent_verification: {
    tr: "5. Bağımsız Doğrulama ve Kanıt Kontrolü",
    en: "5. Independent Verification Layer",
  },
  human_review: {
    tr: "İnsan Onay Süreci",
    en: "Human Approval Step",
  },
};

export const AnalysisPipelineProgress: React.FC<AnalysisPipelineProgressProps> = ({
  isAnalyzing,
  stageResults,
  verificationStatus,
  error,
  onRetry,
  quoteCount = 2,
}) => {
  const { t, locale } = useTranslation();
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isCompletedExpanded, setIsCompletedExpanded] = useState(false);

  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    if (isAnalyzing) {
      setElapsedSeconds(0);
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      if (timer) clearInterval(timer);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isAnalyzing]);

  const formatTimer = (totalSec: number) => {
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const formatDuration = (ms: number | undefined | null) => {
    if (ms === undefined || ms === null || isNaN(ms)) return "-";
    if (ms >= 1000) {
      return `${(ms / 1000).toFixed(2)} s`;
    }
    return `${Math.round(ms)} ms`;
  };

  const getStageTitle = (stageKey: string) => {
    const entry = STAGE_NAME_MAP[stageKey];
    if (entry) {
      return locale === "en" ? entry.en : entry.tr;
    }
    return stageKey.replace(/_/g, " ").toUpperCase();
  };

  const stages = [
    {
      id: "deterministic_evaluation",
      icon: <Calculator size={18} className="text-blue-500" />,
      title: t("rfq_detail.analysis_pipeline_progress.stage_1_title"),
      desc: t("rfq_detail.analysis_pipeline_progress.stage_1_desc"),
    },
    {
      id: "policy_compliance",
      icon: <FileSearch size={18} className="text-purple-500" />,
      title: t("rfq_detail.analysis_pipeline_progress.stage_2_title"),
      desc: t("rfq_detail.analysis_pipeline_progress.stage_2_desc"),
    },
    {
      id: "supplier_history",
      icon: <Database size={18} className="text-amber-500" />,
      title: t("rfq_detail.analysis_pipeline_progress.stage_3_title"),
      desc: t("rfq_detail.analysis_pipeline_progress.stage_3_desc"),
    },
    {
      id: "supplier_recommendation",
      icon: <Sparkles size={18} className="text-emerald-500" />,
      title: t("rfq_detail.analysis_pipeline_progress.stage_4_title"),
      desc: t("rfq_detail.analysis_pipeline_progress.stage_4_desc"),
    },
    {
      id: "independent_verification",
      icon: <ShieldCheck size={18} className="text-cyan-500" />,
      title: t("rfq_detail.analysis_pipeline_progress.stage_5_title"),
      desc: t("rfq_detail.analysis_pipeline_progress.stage_5_desc"),
    },
  ];

  // ── Render Error State ───────────────────────────────────────────────────
  if (error && !isAnalyzing) {
    return (
      <div className="p-5 rounded-xl bg-danger/10 border border-danger/25 text-danger shadow-sm mb-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-danger/20 text-danger shrink-0 mt-0.5">
              <AlertTriangle size={18} />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-text-primary">
                {t("common.status.failed") || "Analiz Hatası"}
              </h4>
              <p className="text-xs text-text-secondary mt-1">{error}</p>
            </div>
          </div>
          {onRetry && (
            <button
              onClick={onRetry}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-danger text-white hover:bg-danger/90 transition-colors shrink-0 shadow-sm"
            >
              <RefreshCw size={13} />
              {t("rfq_detail.analysis_pipeline_progress.btn_retry")}
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Render Active Analysis Pipeline Stepper ──────────────────────────────
  if (isAnalyzing) {
    return (
      <div className="p-6 rounded-xl bg-surface-elevated border border-primary/30 shadow-md mb-6 relative overflow-hidden animate-in fade-in duration-200">
        {/* Animated Top Progress Glow Line */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary/20 via-primary to-primary/20 animate-pulse" />

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/25 text-primary flex items-center justify-center shrink-0">
              <Sparkles size={20} className="animate-spin text-primary" style={{ animationDuration: "3s" }} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-text-primary">
                  {t("rfq_detail.analysis_pipeline_progress.title")}
                </h3>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary/15 text-primary border border-primary/30">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary animate-ping" />
                  {t("rfq_detail.analysis_pipeline_progress.in_progress_badge")}
                </span>
              </div>
              <p className="text-xs text-text-muted mt-0.5">
                {t("rfq_detail.analysis_pipeline_progress.subtitle")}
              </p>
            </div>
          </div>

          {/* Live Timer Pill */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface border border-border self-start sm:self-auto shrink-0 shadow-inner">
            <Clock size={14} className="text-text-muted" />
            <span className="text-xs text-text-muted">{t("rfq_detail.quote_extraction_progress.elapsed_time")}:</span>
            <span className="font-mono text-xs font-bold text-primary">
              {formatTimer(elapsedSeconds)}
            </span>
          </div>
        </div>

        {/* Pipeline Stage Steps */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {stages.map((stage, idx) => (
            <div
              key={stage.id}
              className="p-3.5 rounded-lg bg-surface/60 border border-border flex flex-col justify-between transition-all hover:bg-surface/90"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="w-7 h-7 rounded-lg bg-surface-elevated border border-border flex items-center justify-center">
                    {stage.icon}
                  </div>
                  <span className="text-[10px] font-mono font-bold text-text-muted">
                    0{idx + 1}
                  </span>
                </div>
                <h4 className="text-xs font-semibold text-text-primary leading-tight mb-1">
                  {stage.title}
                </h4>
                <p className="text-[11px] text-text-muted leading-relaxed">
                  {stage.desc}
                </p>
              </div>

              {/* Step Label Footer */}
              <div className="mt-3 pt-2 border-t border-border/50 flex items-center justify-between text-[10px]">
                <span className="text-text-muted font-medium">
                  {locale === "en" ? `Stage 0${idx + 1}` : `Aşama 0${idx + 1}`}
                </span>
                <span className="text-[10px] font-mono text-text-muted">~{quoteCount} {locale === "en" ? "quotes" : "teklif"}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Honest Server Processing Notice */}
        <div className="mt-4 p-3 rounded-lg bg-primary/5 border border-primary/15 flex items-center gap-2 text-xs text-text-secondary">
          <RefreshCw size={14} className="animate-spin text-primary shrink-0" />
          <span>{t("rfq_detail.analysis_pipeline_progress.server_processing")}</span>
        </div>
      </div>
    );
  }

  // ── Completed Stages Drawer (Evidence Traceability) ──────────────────────
  if (stageResults && stageResults.length > 0) {
    const hasFailedStage = stageResults.some((s) => s.status === "failed");
    const isVerificationFailed = verificationStatus === "failed" || verificationStatus === "overridden";
    const isAllPassed = !hasFailedStage && !isVerificationFailed;

    return (
      <div className="mb-6 rounded-xl bg-surface-elevated border border-border shadow-sm overflow-hidden">
        <button
          type="button"
          onClick={() => setIsCompletedExpanded(!isCompletedExpanded)}
          className="w-full px-5 py-3.5 flex items-center justify-between bg-surface/40 hover:bg-surface-hover transition-colors text-left"
        >
          <div className="flex items-center gap-2.5">
            {isAllPassed ? (
              <CheckCircle2 size={16} className="text-emerald-500 shrink-0" />
            ) : (
              <AlertTriangle size={16} className="text-amber-500 shrink-0" />
            )}
            <span className="text-xs font-semibold text-text-primary">
              {isAllPassed
                ? `${t("rfq_detail.analysis_pipeline_progress.completed_badge")} (${stageResults.length}/5)`
                : t("rfq_detail.analysis_pipeline_progress.alert_badge")}
            </span>
            <span className="hidden sm:inline-block text-[11px] text-text-muted">
              • {isAllPassed
                  ? t("rfq_detail.analysis_pipeline_progress.completed_summary")
                  : t("rfq_detail.analysis_pipeline_progress.alert_summary")}
            </span>
          </div>
          <div className="flex items-center gap-2 text-text-muted text-xs font-medium">
            <span>{isCompletedExpanded ? t("common.actions.collapse") || "Gizle" : t("common.actions.details") || "Aşama Detayları"}</span>
            {isCompletedExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </div>
        </button>

        {isCompletedExpanded && (
          <div className="p-4 border-t border-border bg-surface/20 divide-y divide-border/60">
            {stageResults.map((stg, i) => {
              const isStageFailed = stg.status === "failed";
              const isStageInconclusive = stg.status === "inconclusive";

              return (
                <div key={stg.stage || i} className="py-2.5 first:pt-0 last:pb-0 flex items-start justify-between gap-3 text-xs">
                  <div className="flex items-start gap-2">
                    {isStageFailed ? (
                      <span className="w-5 h-5 rounded-full bg-rose-500/15 text-rose-500 flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5" title="Failed">
                        ✕
                      </span>
                    ) : isStageInconclusive ? (
                      <span className="w-5 h-5 rounded-full bg-amber-500/15 text-amber-500 flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5" title="Inconclusive">
                        !
                      </span>
                    ) : (
                      <span className="w-5 h-5 rounded-full bg-emerald-500/15 text-emerald-500 flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5" title="Completed">
                        ✓
                      </span>
                    )}
                    <div>
                      <span className="font-semibold text-text-primary text-[11px]">
                        {getStageTitle(stg.stage)}
                      </span>
                      {stg.summary && (
                        <p className="text-text-muted text-[11px] mt-0.5">{stg.summary}</p>
                      )}
                    </div>
                  </div>
                  <span className="font-mono text-[11px] text-text-muted shrink-0 bg-surface px-2 py-0.5 rounded border border-border">
                    {formatDuration(stg.duration_ms)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return null;
};
