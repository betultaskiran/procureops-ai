"use client";

import React, { useState } from "react";
import { 
  ShieldCheck, 
  ShieldAlert,
  AlertTriangle, 
  CheckCircle, 
  XCircle, 
  FileText, 
  Lock, 
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Award,
  Layers,
  Clock,
  Check,
  TrendingUp,
  DollarSign
} from "lucide-react";
import { AnalysisResponse, Quote } from "@/lib/api/types";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency as fmtCurrency } from "@/lib/i18n/formatters";

interface EvidencePanelProps {
  analysis: AnalysisResponse;
  quotes: Quote[];
  onOpenReviewModal?: (quoteId?: string) => void;
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({
  analysis,
  quotes,
  onOpenReviewModal,
}) => {
  const { t, locale } = useTranslation();
  const [isRulesExpanded, setIsRulesExpanded] = useState(false);
  const [selectedEvidenceIdx, setSelectedEvidenceIdx] = useState<number | null>(null);

  const recommendation = analysis.recommendation;
  const recommendedQuote = quotes.find(
    (q) => q.id === recommendation?.recommended_quote_id
  );

  const formatVerificationStatus = (status?: string) => {
    switch (status?.toLowerCase()) {
      case "verified":
      case "passed":
        return {
          label: t("analysis.evidence.v_status_verified"),
          bg: "bg-emerald-500/15",
          border: "border-emerald-500/30",
          text: "text-emerald-400",
          dot: "bg-emerald-400",
        };
      case "failed":
      case "overridden":
        return {
          label: t("analysis.evidence.v_status_failed"),
          bg: "bg-red-500/15",
          border: "border-red-500/30",
          text: "text-red-400",
          dot: "bg-red-400",
        };
      case "inconclusive":
        return {
          label: t("analysis.evidence.v_status_inconclusive"),
          bg: "bg-amber-500/15",
          border: "border-amber-500/30",
          text: "text-amber-400",
          dot: "bg-amber-400",
        };
      case "exception_required":
        return {
          label: t("analysis.evidence.v_status_exception_required"),
          bg: "bg-red-500/15",
          border: "border-red-500/30",
          text: "text-red-400",
          dot: "bg-red-400",
        };
      default:
        return {
          label: t("analysis.evidence.v_status_pending"),
          bg: "bg-amber-500/15",
          border: "border-amber-500/30",
          text: "text-amber-400",
          dot: "bg-amber-400",
        };
    }
  };

  const statusStyle = formatVerificationStatus(recommendation?.verification_status);

  // Group compliance checks by quote
  const checksByQuote = quotes.map((q) => {
    const checks = analysis.compliance_checks?.filter((c) => c.quote_id === q.id) || [];
    return {
      quote: q,
      checks,
    };
  });

  // 6 Pipeline Stages definition
  const defaultStages = [
    {
      name: t("analysis.evidence.stage_1_name"),
      fullName: t("analysis.evidence.stage_1_desc"),
      type: t("analysis.evidence.stage_1_type"),
      status: "completed",
    },
    {
      name: t("analysis.evidence.stage_2_name"),
      fullName: t("analysis.evidence.stage_2_desc"),
      type: t("analysis.evidence.stage_2_type"),
      status: "completed",
    },
    {
      name: t("analysis.evidence.stage_3_name"),
      fullName: t("analysis.evidence.stage_3_desc"),
      type: t("analysis.evidence.stage_3_type"),
      status: analysis.evidence_items && analysis.evidence_items.length > 0 ? "completed" : "inconclusive",
    },
    {
      name: t("analysis.evidence.stage_4_name"),
      fullName: t("analysis.evidence.stage_4_desc"),
      type: t("analysis.evidence.stage_4_type"),
      status: recommendation ? "completed" : "pending",
    },
    {
      name: t("analysis.evidence.stage_5_name"),
      fullName: t("analysis.evidence.stage_5_desc"),
      type: t("analysis.evidence.stage_5_type"),
      status: recommendation?.verification_status?.toLowerCase() === "failed" || recommendation?.verification_status?.toLowerCase() === "overridden"
        ? "failed"
        : recommendation?.verification_status?.toLowerCase() === "inconclusive"
        ? "inconclusive"
        : "completed",
    },
    {
      name: t("analysis.evidence.stage_6_name"),
      fullName: t("analysis.evidence.stage_6_desc"),
      type: t("analysis.evidence.stage_6_type"),
      status: "pending",
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* ── 6-Aşamalı Karar ve Doğrulama Akışı (Stage Pipeline) ──────── */}
      <div className="bg-surface-elevated border border-border rounded-xl p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-primary" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-primary">
              {t("analysis.evidence.pipeline_title")}
            </h3>
          </div>
          <span className="text-[11px] text-text-muted">
            {t("analysis.evidence.pipeline_subtitle")}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
          {defaultStages.map((stage, idx) => {
            const isCompleted = stage.status === "completed";
            const isFailed = stage.status === "failed";
            const isInconclusive = stage.status === "inconclusive";

            return (
              <div
                key={idx}
                className={`p-2.5 rounded-lg border text-xs flex flex-col justify-between ${
                  isCompleted
                    ? "bg-emerald-500/5 border-emerald-500/20"
                    : isFailed
                    ? "bg-red-500/5 border-red-500/20"
                    : isInconclusive
                    ? "bg-amber-500/5 border-amber-500/20"
                    : "bg-surface/50 border-border"
                }`}
              >
                <div className="flex items-center justify-between gap-1 mb-1">
                  <span className="text-[10px] font-bold text-text-muted">
                    {stage.name}
                  </span>
                  {isCompleted ? (
                    <CheckCircle size={12} className="text-emerald-400 shrink-0" />
                  ) : isFailed ? (
                    <XCircle size={12} className="text-red-400 shrink-0" />
                  ) : isInconclusive ? (
                    <AlertTriangle size={12} className="text-amber-400 shrink-0" />
                  ) : (
                    <Clock size={12} className="text-text-muted shrink-0" />
                  )}
                </div>

                <div>
                  <span className="font-semibold text-text-primary text-[11px] block truncate">
                    {stage.fullName}
                  </span>
                  <span className="text-[10px] text-text-muted block mt-0.5">
                    {stage.type}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── AI Recommendation Card ────────────────────────────────────── */}
      <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 pb-4 border-b border-border">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <Sparkles size={16} />
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-text-primary">
                {t("analysis.evidence.engine_title")}
              </h2>
              <span className="text-xs text-text-muted">
                {t("analysis.evidence.engine_subtitle")}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${statusStyle.bg} ${statusStyle.border} ${statusStyle.text}`}
            >
              <span className={`w-2 h-2 rounded-full ${statusStyle.dot}`} />
              {statusStyle.label}
            </span>
          </div>
        </div>

        {/* Stale Analysis Warning */}
        {analysis.is_stale && (
          <div className="mb-5 p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2.5">
            <AlertTriangle size={16} className="text-amber-400 shrink-0" />
            <span>
              {t("analysis.evidence.stale_warning")}
            </span>
          </div>
        )}

        {/* Highlighted Recommended Supplier */}
        {recommendedQuote ? (
          <div className={`mb-5 p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
            analysis.is_stale
              ? "bg-surface/50 border-border opacity-70"
              : recommendation?.verification_status?.toLowerCase() === "failed" || recommendation?.verification_status?.toLowerCase() === "overridden"
              ? "bg-red-500/5 border-red-500/30"
              : recommendation?.verification_status?.toLowerCase() === "inconclusive"
              ? "bg-amber-500/5 border-amber-500/30"
              : "bg-surface/70 border-border"
          }`}>
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold border ${
                analysis.is_stale
                  ? "bg-zinc-800 text-zinc-400 border-zinc-700"
                  : recommendation?.verification_status?.toLowerCase() === "failed" || recommendation?.verification_status?.toLowerCase() === "overridden"
                  ? "bg-red-500/15 text-red-400 border-red-500/30"
                  : recommendation?.verification_status?.toLowerCase() === "inconclusive"
                  ? "bg-amber-500/15 text-amber-400 border-amber-500/30"
                  : "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
              }`}>
                {recommendation?.verification_status?.toLowerCase() === "failed" || recommendation?.verification_status?.toLowerCase() === "overridden" ? (
                  <XCircle size={20} />
                ) : recommendation?.verification_status?.toLowerCase() === "inconclusive" ? (
                  <AlertTriangle size={20} />
                ) : (
                  <Award size={20} />
                )}
              </div>
              <div>
                <span className={`text-[11px] uppercase tracking-wider font-bold block ${
                  recommendation?.verification_status?.toLowerCase() === "failed" || recommendation?.verification_status?.toLowerCase() === "overridden"
                    ? "text-red-400"
                    : recommendation?.verification_status?.toLowerCase() === "inconclusive"
                    ? "text-amber-400"
                    : "text-text-muted"
                }`}>
                  {analysis.is_stale
                    ? t("analysis.evidence.badge_stale")
                    : recommendation?.verification_status?.toLowerCase() === "failed" || recommendation?.verification_status?.toLowerCase() === "overridden"
                    ? t("analysis.evidence.badge_failed")
                    : recommendation?.verification_status?.toLowerCase() === "inconclusive"
                    ? t("analysis.evidence.badge_inconclusive")
                    : t("analysis.evidence.badge_recommended")}
                </span>
                <span className="text-base font-bold text-text-primary">
                  {recommendedQuote.supplier_name || t("analysis.matrix.unknown_supplier")}
                </span>
                <span className="text-xs text-text-muted block mt-0.5">
                  {t("analysis.evidence.total_price_label", { price: fmtCurrency(recommendedQuote.total_price, recommendedQuote.currency || "TRY", locale) })}
                  {recommendedQuote.delivery_days ? ` • ${t("analysis.matrix.days_unit", { count: recommendedQuote.delivery_days })}` : ""}
                  {recommendedQuote.warranty_months ? ` • ${t("analysis.matrix.months_unit", { count: recommendedQuote.warranty_months })}` : ""}
                </span>
              </div>
            </div>

            {onOpenReviewModal && (
              <button
                onClick={() => onOpenReviewModal(recommendedQuote.id)}
                className={`px-4 py-2 rounded-lg text-xs font-semibold text-white transition-colors shadow-sm flex items-center gap-1.5 self-start sm:self-auto ${
                  analysis.is_stale
                    ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-300"
                    : recommendation?.verification_status?.toLowerCase() === "failed" || recommendation?.verification_status?.toLowerCase() === "overridden"
                    ? "bg-red-600 hover:bg-red-500"
                    : recommendation?.verification_status?.toLowerCase() === "inconclusive"
                    ? "bg-amber-600 hover:bg-amber-500"
                    : "bg-emerald-600 hover:bg-emerald-500"
                }`}
              >
                {analysis.is_stale ? (
                  <>
                    <Clock size={14} />
                    {t("analysis.evidence.btn_stale")}
                  </>
                ) : recommendation?.verification_status?.toLowerCase() === "inconclusive" ? (
                  <>
                    <ShieldAlert size={14} />
                    {t("analysis.evidence.btn_inconclusive")}
                  </>
                ) : recommendation?.verification_status?.toLowerCase() === "failed" || recommendation?.verification_status?.toLowerCase() === "overridden" ? (
                  <>
                    <XCircle size={14} />
                    {t("analysis.evidence.btn_violation")}
                  </>
                ) : (
                  <>
                    <CheckCircle size={14} />
                    {t("analysis.evidence.btn_approve")}
                  </>
                )}
              </button>
            )}
          </div>
        ) : (
          <div className="mb-5 p-4 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300">
            {t("analysis.evidence.no_recommendation")}
          </div>
        )}

        {/* Reasoning Text */}
        <div className="mb-5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
            {t("analysis.evidence.reasoning_title")}
          </h3>
          <div className="p-4 rounded-lg bg-surface/40 border border-border text-xs text-text-secondary leading-relaxed">
            {recommendation?.reasoning || t("analysis.evidence.no_reasoning")}
          </div>
        </div>

        {/* Risks & Verification Notes Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
          {recommendation?.risks && (
            <div className="p-4 rounded-lg bg-amber-500/5 border border-amber-500/20">
              <h4 className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                <AlertTriangle size={13} />
                {t("analysis.evidence.risks_title")}
              </h4>
              <p className="text-xs text-text-muted leading-relaxed">
                {recommendation.risks}
              </p>
            </div>
          )}

          {recommendation?.alternative_notes && (
            <div className="p-4 rounded-lg bg-surface/40 border border-border">
              <h4 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                <FileText size={13} className="text-primary" />
                {t("analysis.evidence.alternatives_title")}
              </h4>
              <p className="text-xs text-text-muted leading-relaxed">
                {recommendation.alternative_notes}
              </p>
            </div>
          )}
        </div>

        {recommendation?.verification_notes && (
          <div className="text-xs text-text-muted border-t border-border pt-3">
            <span className="font-semibold text-text-primary">{t("analysis.evidence.verification_notes_prefix")}</span>
            {recommendation.verification_notes}
          </div>
        )}
      </div>

      {/* ── Policy Evidence Citations (RAG Kanıtları) ──────────────────── */}
      {analysis.evidence_items && analysis.evidence_items.length > 0 && (
        <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FileText size={16} className="text-primary" />
              <h3 className="text-sm font-semibold uppercase tracking-wider text-text-primary">
                {t("analysis.evidence.rag_citations_heading", { count: analysis.evidence_items.length })}
              </h3>
            </div>
            <span className="text-xs text-text-muted">
              {t("analysis.evidence.rag_citations_subheading")}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {analysis.evidence_items.map((item, idx) => {
              const isFx = item.source_type === "fx_rate" || item.source_type === "currency_conversion";
              return (
                <div
                  key={idx}
                  className={`p-3.5 rounded-lg border flex flex-col justify-between transition-colors ${
                    isFx
                      ? "bg-blue-500/5 border-blue-500/30 hover:border-blue-500/50"
                      : "bg-surface/50 border-border hover:border-primary/40"
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-1.5 flex-wrap">
                      <span
                        className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border inline-flex items-center gap-1 ${
                          isFx
                            ? "bg-blue-500/15 text-blue-300 border-blue-500/30"
                            : "bg-primary/10 text-primary border border-primary/20"
                        }`}
                      >
                        {isFx && <TrendingUp size={11} className="text-blue-400" />}
                        {isFx ? t("analysis.evidence.fx_evidence_badge") : item.source_type}
                      </span>
                      <span className="text-[11px] font-mono text-text-muted">
                        {item.source_reference}
                      </span>
                    </div>
                    <p className="text-xs text-text-primary font-medium leading-relaxed mt-1">
                      &ldquo;{item.claim}&rdquo;
                    </p>
                    {item.content && (
                      <div className="mt-2 p-2 rounded bg-surface/80 border border-border/70 text-[11px] font-mono text-text-secondary leading-relaxed break-words">
                        {item.content}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Deterministic Rule Checks (Hard Rules) ─────────────────────── */}
      <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Lock size={16} className="text-primary" />
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wider text-text-primary">
                {t("analysis.evidence.hard_rules_title")}
              </h3>
              <span className="text-xs text-text-muted">
                {t("analysis.evidence.hard_rules_subtitle")}
              </span>
            </div>
          </div>

          <button
            onClick={() => setIsRulesExpanded(!isRulesExpanded)}
            className="flex items-center gap-1 text-xs text-primary hover:underline font-medium"
          >
            {isRulesExpanded ? (
              <>
                <span>{t("analysis.evidence.collapse_rules")}</span>
                <ChevronUp size={14} />
              </>
            ) : (
              <>
                <span>{t("analysis.evidence.expand_rules")}</span>
                <ChevronDown size={14} />
              </>
            )}
          </button>
        </div>

        {/* Safety Guardrail Notice */}
        <div className="p-3.5 rounded-lg bg-surface/60 border border-border text-xs text-text-muted leading-relaxed mb-4">
          <span className="font-semibold text-text-primary block mb-0.5">
            {t("analysis.evidence.guardrail_notice_title")}
          </span>
          {t("analysis.evidence.guardrail_notice_body")}
        </div>

        {isRulesExpanded && (
          <div className="space-y-4 pt-2">
            {checksByQuote.map(({ quote, checks }) => (
              <div key={quote.id} className="border border-border rounded-lg overflow-hidden bg-surface/30">
                <div className="p-3 bg-surface/60 border-b border-border flex items-center justify-between">
                  <span className="text-xs font-bold text-text-primary">
                    {quote.supplier_name || t("analysis.matrix.unknown_supplier")}
                  </span>
                  <span className="text-[11px] text-text-muted">
                    {t("analysis.evidence.rules_inspected_count", { count: checks.length })}
                  </span>
                </div>

                <div className="divide-y divide-border">
                  {checks.length === 0 ? (
                    <div className="p-3 text-xs text-text-muted">{t("analysis.evidence.no_rule_records")}</div>
                  ) : (
                    checks.map((check, idx) => {
                      const isPass = check.result === "pass";
                      const isFail = check.result === "fail";

                      return (
                        <div key={idx} className="p-3 flex items-start gap-3 text-xs">
                          {isPass ? (
                            <CheckCircle size={15} className="text-emerald-400 shrink-0 mt-0.5" />
                          ) : isFail ? (
                            <XCircle size={15} className="text-red-400 shrink-0 mt-0.5" />
                          ) : (
                            <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
                          )}

                          <div className="flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-semibold text-text-primary">
                                {check.rule_description || check.rule_name}
                              </span>
                              <span
                                className={`font-mono text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${
                                  isPass
                                    ? "bg-emerald-500/10 text-emerald-400"
                                    : isFail
                                    ? "bg-red-500/10 text-red-400"
                                    : "bg-amber-500/10 text-amber-400"
                                }`}
                              >
                                {check.result.toUpperCase()}
                              </span>
                            </div>

                            <p className="text-text-muted mt-0.5">{check.notes}</p>
                            
                            <div className="mt-1 flex items-center gap-3 text-[11px] text-text-muted font-mono">
                              <span>{t("analysis.evidence.actual_value_label")}<strong className="text-text-primary">{check.actual_value}</strong></span>
                              <span>•</span>
                              <span>{t("analysis.evidence.required_value_label")}<strong className="text-text-primary">{check.required_value}</strong></span>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
