"use client";

import React, { useState } from "react";
import { 
  X, 
  CheckCircle, 
  AlertTriangle, 
  XCircle, 
  RotateCcw, 
  Loader2, 
  ShieldAlert, 
  FileCheck,
  Check,
  Building
} from "lucide-react";
import { Quote, AnalysisResponse, ReviewRequest, ReviewResponse } from "@/lib/api/types";
import { rfqsApi } from "@/lib/api/rfqs";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency as fmtCurrency } from "@/lib/i18n/formatters";

interface ReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  analysis: AnalysisResponse;
  quotes: Quote[];
  initialSelectedQuoteId?: string | null;
  onSuccess: (review: ReviewResponse) => void;
}

export const ReviewModal: React.FC<ReviewModalProps> = ({
  isOpen,
  onClose,
  analysis,
  quotes,
  initialSelectedQuoteId,
  onSuccess,
}) => {
  const { t, locale } = useTranslation();
  const recommendedQuoteId = analysis.recommendation?.recommended_quote_id;

  const vStatus = analysis.recommendation?.verification_status?.toLowerCase();
  const isVerificationInconclusive = vStatus === "inconclusive";
  const isVerificationFailed = vStatus === "failed" || vStatus === "overridden";
  const isStale = Boolean(analysis.is_stale);

  const initialTargetId = initialSelectedQuoteId || recommendedQuoteId || quotes[0]?.id || "";
  const initialQuote = quotes.find((q) => q.id === initialTargetId);
  const initialChecks = analysis.compliance_checks?.filter((c) => c.quote_id === initialTargetId) || [];
  const initialIsNonCompliant = initialQuote?.is_compliant === false || initialChecks.some((c) => c.result === "fail");
  const initialBlocked = initialIsNonCompliant || isVerificationInconclusive || isVerificationFailed || isStale;

  const [selectedQuoteId, setSelectedQuoteId] = useState<string>(initialTargetId);
  const [reviewStatus, setReviewStatus] = useState<string>("approved");
  const [comment, setComment] = useState("");
  const [acknowledgedViolation, setAcknowledgedViolation] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successResult, setSuccessResult] = useState<ReviewResponse | null>(null);

  if (!isOpen) return null;

  const chosenQuote = quotes.find((q) => q.id === selectedQuoteId);
  const quoteChecks = analysis.compliance_checks?.filter((c) => c.quote_id === selectedQuoteId) || [];
  const isNonCompliant = chosenQuote?.is_compliant === false || quoteChecks.some((c) => c.result === "fail");

  const isStandardApprovalBlocked = isNonCompliant || isVerificationInconclusive || isVerificationFailed || isStale;

  const isSubmitDisabled =
    isSubmitting ||
    !selectedQuoteId ||
    isStale ||
    (reviewStatus === "approved" && isStandardApprovalBlocked) ||
    (reviewStatus === "exception_approved" && (!acknowledgedViolation || isStale)) ||
    ((reviewStatus === "rejected" || reviewStatus === "revision_requested") && (!comment.trim() || isStale));

  const handleSubmit = async () => {
    try {
      setIsSubmitting(true);
      setErrorMessage(null);

      const payload: ReviewRequest = {
        status: reviewStatus,
        comment: comment.trim() || undefined,
        selected_quote_id: selectedQuoteId,
        acknowledged_policy_violation: reviewStatus === "exception_approved" ? acknowledgedViolation : false,
      };

      const res = await rfqsApi.reviewAnalysis(analysis.id, payload);
      setSuccessResult(res);
      onSuccess(res);
    } catch (err: any) {
      setErrorMessage(err.message || "An error occurred during operation.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-surface-elevated border border-border rounded-xl shadow-2xl max-w-xl w-full overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="p-5 border-b border-border flex items-center justify-between bg-surface/50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
              <FileCheck size={16} />
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-text-primary">
                {t("analysis.review.header_title")}
              </h2>
              <span className="text-xs text-text-muted">
                {t("analysis.review.header_subtitle")}
              </span>
            </div>
          </div>

          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="text-text-muted hover:text-text-primary transition-colors p-1"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-5">
          {successResult ? (
            <div className="p-6 text-center space-y-4">
              <div className="w-14 h-14 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 mx-auto flex items-center justify-center">
                <CheckCircle size={32} />
              </div>
              <h3 className="text-lg font-bold text-text-primary">
                {t("analysis.review.success_title")}
              </h3>
              <p className="text-xs text-text-muted max-w-md mx-auto leading-relaxed">
                {reviewStatus === "approved" || reviewStatus === "exception_approved"
                  ? t("analysis.review.success_desc_po")
                  : t("analysis.review.success_desc_general")}
              </p>

              <div className="p-4 rounded-lg bg-surface border border-border text-xs text-left space-y-1.5 font-mono">
                <div className="flex justify-between">
                  <span className="text-text-muted">{t("analysis.review.status_label")}</span>
                  <span className="font-semibold uppercase text-emerald-400">{successResult.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">{t("analysis.review.selected_quote_label")}</span>
                  <span className="text-text-primary">{successResult.selected_quote_id || "-"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">{t("analysis.review.exception_ack_label")}</span>
                  <span>{successResult.acknowledged_policy_violation ? t("analysis.review.yes_confirmed") : t("analysis.review.no")}</span>
                </div>
              </div>

              <button
                onClick={() => {
                  onClose();
                  window.location.reload();
                }}
                className="w-full py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-semibold transition-colors shadow-sm"
              >
                {t("analysis.review.complete_and_refresh")}
              </button>
            </div>
          ) : (
            <>
              {/* Quote Selector */}
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-text-muted block mb-2">
                  {t("analysis.review.step1_title")}
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {quotes.map((q) => {
                    const isRec = q.id === recommendedQuoteId;
                    const isSel = q.id === selectedQuoteId;
                    const qChecks = analysis.compliance_checks?.filter((c) => c.quote_id === q.id) || [];
                    const qHasFail = q.is_compliant === false || qChecks.some((c) => c.result === "fail");

                    return (
                      <button
                        key={q.id}
                        type="button"
                        onClick={() => {
                          setSelectedQuoteId(q.id);
                        }}
                        className={`p-3 rounded-lg border text-left transition-all relative ${
                          isSel
                            ? "bg-primary/10 border-primary ring-1 ring-primary"
                            : "bg-surface/50 border-border hover:bg-surface"
                        }`}
                      >
                        {isRec && (
                          <span className="absolute top-2 right-2 text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-semibold">
                            {t("analysis.review.ai_badge")}
                          </span>
                        )}
                        <div className="font-semibold text-xs text-text-primary pr-12 truncate">
                          {q.supplier_name || t("analysis.matrix.unknown_supplier")}
                        </div>
                        <div className="text-xs font-mono font-bold text-text-secondary mt-1">
                          {fmtCurrency(q.total_price, q.currency || "TRY", locale)}
                        </div>
                        <div className="mt-1 flex items-center gap-1.5 text-[11px]">
                          {qHasFail ? (
                            <span className="text-red-400 flex items-center gap-1">
                              <XCircle size={11} /> {t("analysis.review.rule_violation")}
                            </span>
                          ) : (
                            <span className="text-emerald-400 flex items-center gap-1">
                              <CheckCircle size={11} /> {t("analysis.review.compliant")}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Decision Options */}
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-text-muted block mb-2">
                  {t("analysis.review.step2_title")}
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {/* Standart Onay */}
                  <button
                    type="button"
                    onClick={() => setReviewStatus("approved")}
                    disabled={isStandardApprovalBlocked}
                    className={`p-3 rounded-lg border text-left text-xs transition-all ${
                      reviewStatus === "approved"
                        ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 ring-1 ring-emerald-500"
                        : isStandardApprovalBlocked
                        ? "bg-surface/20 border-border text-zinc-600 cursor-not-allowed opacity-50"
                        : "bg-surface/50 border-border hover:bg-surface text-text-primary"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      <CheckCircle size={14} className={isStandardApprovalBlocked ? "text-zinc-600" : "text-emerald-400"} />
                      {t("analysis.review.opt_standard_title")}
                    </div>
                    <span className="text-[11px] text-text-muted block mt-1">
                      {isStale
                        ? t("analysis.review.blocked_stale")
                        : isVerificationInconclusive
                        ? t("analysis.review.blocked_inconclusive")
                        : isVerificationFailed
                        ? t("analysis.review.blocked_failed")
                        : isNonCompliant
                        ? t("analysis.review.blocked_non_compliant")
                        : t("analysis.review.opt_standard_desc")}
                    </span>
                  </button>

                  {/* İstisna Onayı */}
                  <button
                    type="button"
                    onClick={() => setReviewStatus("exception_approved")}
                    disabled={isStale}
                    className={`p-3 rounded-lg border text-left text-xs transition-all ${
                      reviewStatus === "exception_approved"
                        ? "bg-amber-500/15 border-amber-500/40 text-amber-300 ring-1 ring-amber-500"
                        : isStale
                        ? "bg-surface/20 border-border text-zinc-600 cursor-not-allowed opacity-50"
                        : "bg-surface/50 border-border hover:bg-surface text-text-primary"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      <ShieldAlert size={14} className="text-amber-400" />
                      {t("analysis.review.opt_exception_title")}
                    </div>
                    <span className="text-[11px] text-text-muted block mt-1">
                      {t("analysis.review.opt_exception_desc")}
                    </span>
                  </button>

                  {/* Revizyon Talebi */}
                  <button
                    type="button"
                    onClick={() => setReviewStatus("revision_requested")}
                    disabled={isStale}
                    className={`p-3 rounded-lg border text-left text-xs transition-all ${
                      reviewStatus === "revision_requested"
                        ? "bg-blue-500/15 border-blue-500/40 text-blue-300 ring-1 ring-blue-500"
                        : isStale
                        ? "bg-surface/20 border-border text-zinc-600 cursor-not-allowed opacity-50"
                        : "bg-surface/50 border-border hover:bg-surface text-text-primary"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      <RotateCcw size={14} className="text-blue-400" />
                      {t("analysis.review.opt_revision_title")}
                    </div>
                    <span className="text-[11px] text-text-muted block mt-1">
                      {t("analysis.review.opt_revision_desc")}
                    </span>
                  </button>

                  {/* Reddet */}
                  <button
                    type="button"
                    onClick={() => setReviewStatus("rejected")}
                    disabled={isStale}
                    className={`p-3 rounded-lg border text-left text-xs transition-all ${
                      reviewStatus === "rejected"
                        ? "bg-red-500/15 border-red-500/40 text-red-300 ring-1 ring-red-500"
                        : isStale
                        ? "bg-surface/20 border-border text-zinc-600 cursor-not-allowed opacity-50"
                        : "bg-surface/50 border-border hover:bg-surface text-text-primary"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      <XCircle size={14} className="text-red-400" />
                      {t("analysis.review.opt_reject_title")}
                    </div>
                    <span className="text-[11px] text-text-muted block mt-1">
                      {t("analysis.review.opt_reject_desc")}
                    </span>
                  </button>
                </div>
              </div>

              {/* Stale Analysis Alert */}
              {isStale && (
                <div className="p-3.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2.5">
                  <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block mb-0.5">{t("analysis.review.alert_stale_title")}</span>
                    {t("analysis.review.alert_stale_desc")}
                  </div>
                </div>
              )}

              {/* Inconclusive Verification Alert */}
              {!isStale && isVerificationInconclusive && (
                <div className="p-3.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2.5">
                  <ShieldAlert size={16} className="text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block mb-0.5">{t("analysis.review.alert_inconclusive_title")}</span>
                    {t("analysis.review.alert_inconclusive_desc")}
                  </div>
                </div>
              )}

              {/* Failed Verification Alert */}
              {!isStale && isVerificationFailed && (
                <div className="p-3.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-start gap-2.5">
                  <XCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block mb-0.5">{t("analysis.review.alert_failed_title")}</span>
                    {t("analysis.review.alert_failed_desc", { status: analysis.recommendation?.verification_status || "" })}
                  </div>
                </div>
              )}

              {/* Non-compliance guardrail warning */}
              {!isStale && !isVerificationInconclusive && !isVerificationFailed && isNonCompliant && (
                <div className="p-3.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-start gap-2.5">
                  <ShieldAlert size={16} className="text-red-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block mb-0.5">{t("analysis.review.alert_violation_title")}</span>
                    {t("analysis.review.alert_violation_desc")}
                  </div>
                </div>
              )}

              {/* Exception Approval Checkbox */}
              {reviewStatus === "exception_approved" && (
                <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 space-y-3">
                  <div className="flex items-start gap-2.5">
                    <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-amber-300 text-xs block">
                        {t("analysis.review.exception_box_title")}
                      </span>
                      <p className="text-[11px] text-text-muted leading-relaxed mt-0.5">
                        {t("analysis.review.exception_box_desc")}
                      </p>
                    </div>
                  </div>

                  <label className="flex items-start gap-2.5 p-2.5 rounded-lg bg-surface/60 border border-amber-500/20 text-xs text-amber-200 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={acknowledgedViolation}
                      onChange={(e) => setAcknowledgedViolation(e.target.checked)}
                      className="mt-0.5 rounded border-amber-500 text-amber-500 focus:ring-0"
                    />
                    <span className="leading-tight font-medium">
                      {t("analysis.review.exception_checkbox")}
                    </span>
                  </label>
                </div>
              )}

              {/* Comment Field */}
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-text-muted block mb-1.5">
                  {t("analysis.review.step3_title")}{" "}
                  {reviewStatus === "rejected" || reviewStatus === "revision_requested"
                    ? t("analysis.review.required_tag")
                    : t("analysis.review.optional_tag")}
                </label>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={3}
                  placeholder={t("analysis.review.comment_placeholder")}
                  className="w-full text-xs p-3 rounded-lg bg-surface border border-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              {/* Error Message */}
              {errorMessage && (
                <div className="p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                  {errorMessage}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!successResult && (
          <div className="p-4 border-t border-border bg-surface/50 flex justify-end gap-3">
            <button
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
            >
              {t("analysis.review.cancel_btn")}
            </button>

            <button
              onClick={handleSubmit}
              disabled={isSubmitDisabled}
              className={`flex items-center gap-2 px-5 py-2 rounded-lg text-xs font-semibold transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed ${
                reviewStatus === "rejected"
                  ? "bg-red-600 hover:bg-red-500 text-white"
                  : reviewStatus === "exception_approved"
                  ? "bg-amber-600 hover:bg-amber-500 text-white"
                  : "bg-emerald-600 hover:bg-emerald-500 text-white"
              }`}
            >
              {isSubmitting && <Loader2 size={13} className="animate-spin" />}
              <span>
                {isSubmitting
                  ? t("analysis.review.processing_btn")
                  : isStale
                  ? t("analysis.review.reanalysis_required_btn")
                  : reviewStatus === "approved" && isStandardApprovalBlocked
                  ? t("analysis.review.standard_blocked_btn")
                  : reviewStatus === "approved"
                  ? t("analysis.review.standard_approve_btn")
                  : reviewStatus === "exception_approved"
                  ? t("analysis.review.exception_approve_btn")
                  : reviewStatus === "revision_requested"
                  ? t("analysis.review.request_revision_btn")
                  : t("analysis.review.reject_btn")}
              </span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
