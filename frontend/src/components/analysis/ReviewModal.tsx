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
  const recommendedQuoteId = analysis.recommendation?.recommended_quote_id;

  const [selectedQuoteId, setSelectedQuoteId] = useState<string>(
    initialSelectedQuoteId || recommendedQuoteId || quotes[0]?.id || ""
  );

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

  // If the quote is non-compliant and status is "approved", auto-switch to "exception_approved" or notify
  const isStandardApprovalBlocked = isNonCompliant && reviewStatus === "approved";

  const isSubmitDisabled =
    isSubmitting ||
    !selectedQuoteId ||
    isStandardApprovalBlocked ||
    (reviewStatus === "exception_approved" && !acknowledgedViolation) ||
    ((reviewStatus === "rejected" || reviewStatus === "revision_requested") && !comment.trim());

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
      setErrorMessage(err.message || "İşlem sırasında bir hata oluştu.");
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
                Satın Alma Kararını Değerlendir & Onayla
              </h2>
              <span className="text-xs text-text-muted">
                Human-in-the-Loop nihai onay ve Sipariş Emri (PO) üretimi
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
                Karar Başarıyla Kaydedildi!
              </h3>
              <p className="text-xs text-text-muted max-w-md mx-auto leading-relaxed">
                {reviewStatus === "approved" || reviewStatus === "exception_approved"
                  ? "Satın Alma Siparişi (PO) oluşturuldu, bildirim e-postası sıraya alındı ve denetim izi (audit log) güncellendi."
                  : "Değerlendirme durumu güncellendi ve işlem audit kaydı oluşturuldu."}
              </p>

              <div className="p-4 rounded-lg bg-surface border border-border text-xs text-left space-y-1.5 font-mono">
                <div className="flex justify-between">
                  <span className="text-text-muted">Onay Statüsü:</span>
                  <span className="font-semibold uppercase text-emerald-400">{successResult.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Seçilen Teklif ID:</span>
                  <span className="text-text-primary">{successResult.selected_quote_id || "-"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">İstisna Kabulü:</span>
                  <span>{successResult.acknowledged_policy_violation ? "Evet (Teyit Edildi)" : "Hayır"}</span>
                </div>
              </div>

              <button
                onClick={() => {
                  onClose();
                  window.location.reload();
                }}
                className="w-full py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-semibold transition-colors shadow-sm"
              >
                Tamamla ve Sayfayı Güncelle
              </button>
            </div>
          ) : (
            <>
              {/* Quote Selector */}
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-text-muted block mb-2">
                  1. Onaylanacak Teklifi Seçin
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
                          if (qHasFail && reviewStatus === "approved") {
                            setReviewStatus("exception_approved");
                          }
                        }}
                        className={`p-3 rounded-lg border text-left transition-all relative ${
                          isSel
                            ? "bg-primary/10 border-primary ring-1 ring-primary"
                            : "bg-surface/50 border-border hover:bg-surface"
                        }`}
                      >
                        {isRec && (
                          <span className="absolute top-2 right-2 text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-semibold">
                            AI Önerisi
                          </span>
                        )}
                        <div className="font-semibold text-xs text-text-primary pr-12 truncate">
                          {q.supplier_name || "Tedarikçi"}
                        </div>
                        <div className="text-xs font-mono font-bold text-text-secondary mt-1">
                          {new Intl.NumberFormat("tr-TR", { style: "currency", currency: q.currency || "TRY" }).format(q.total_price)}
                        </div>
                        <div className="mt-1 flex items-center gap-1.5 text-[11px]">
                          {qHasFail ? (
                            <span className="text-red-400 flex items-center gap-1">
                              <XCircle size={11} /> Kural İhlali
                            </span>
                          ) : (
                            <span className="text-emerald-400 flex items-center gap-1">
                              <CheckCircle size={11} /> Uygun
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
                  2. Değerlendirme Kararı (Review Status)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {/* Standart Onay */}
                  <button
                    type="button"
                    onClick={() => setReviewStatus("approved")}
                    disabled={isNonCompliant}
                    className={`p-3 rounded-lg border text-left text-xs transition-all ${
                      reviewStatus === "approved"
                        ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 ring-1 ring-emerald-500"
                        : isNonCompliant
                        ? "bg-surface/20 border-border text-zinc-600 cursor-not-allowed opacity-50"
                        : "bg-surface/50 border-border hover:bg-surface text-text-primary"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      <CheckCircle size={14} className="text-emerald-400" />
                      Standart Onay
                    </div>
                    <span className="text-[11px] text-text-muted block mt-1">
                      Kural ihlali olmayan teklif için PO üretir.
                    </span>
                  </button>

                  {/* İstisna Onayı */}
                  <button
                    type="button"
                    onClick={() => setReviewStatus("exception_approved")}
                    className={`p-3 rounded-lg border text-left text-xs transition-all ${
                      reviewStatus === "exception_approved"
                        ? "bg-amber-500/15 border-amber-500/40 text-amber-300 ring-1 ring-amber-500"
                        : "bg-surface/50 border-border hover:bg-surface text-text-primary"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      <ShieldAlert size={14} className="text-amber-400" />
                      İstisna Onayı
                    </div>
                    <span className="text-[11px] text-text-muted block mt-1">
                      Kural aşımını bilerek kabul edip PO üretir.
                    </span>
                  </button>

                  {/* Revizyon Talebi */}
                  <button
                    type="button"
                    onClick={() => setReviewStatus("revision_requested")}
                    className={`p-3 rounded-lg border text-left text-xs transition-all ${
                      reviewStatus === "revision_requested"
                        ? "bg-blue-500/15 border-blue-500/40 text-blue-300 ring-1 ring-blue-500"
                        : "bg-surface/50 border-border hover:bg-surface text-text-primary"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      <RotateCcw size={14} className="text-blue-400" />
                      Revizyon İste
                    </div>
                    <span className="text-[11px] text-text-muted block mt-1">
                      Tedarikçiden revize teklif talep eder.
                    </span>
                  </button>

                  {/* Reddet */}
                  <button
                    type="button"
                    onClick={() => setReviewStatus("rejected")}
                    className={`p-3 rounded-lg border text-left text-xs transition-all ${
                      reviewStatus === "rejected"
                        ? "bg-red-500/15 border-red-500/40 text-red-300 ring-1 ring-red-500"
                        : "bg-surface/50 border-border hover:bg-surface text-text-primary"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      <XCircle size={14} className="text-red-400" />
                      Reddet
                    </div>
                    <span className="text-[11px] text-text-muted block mt-1">
                      Teklif önerisini reddeder.
                    </span>
                  </button>
                </div>
              </div>

              {/* Non-compliance guardrail warning */}
              {isNonCompliant && reviewStatus === "approved" && (
                <div className="p-3.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-start gap-2.5">
                  <ShieldAlert size={16} className="text-red-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block mb-0.5">Standart Onay Engellendi</span>
                    Bu teklif şirket politikası kurallarından (bütçe, teslimat veya garanti) en az birini ihlal etmektedir. Sistemi baypas edip sipariş emri düzenlemek için &ldquo;İstisna Onayı&rdquo; seçilmeli ve kural ihlali açıkça onaylanmalıdır.
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
                        İstisna Onayı & Kural İhlali Teyidi
                      </span>
                      <p className="text-[11px] text-text-muted leading-relaxed mt-0.5">
                        Yasal denetim ve kurumsal yönetişim gereği, şirket politikasına aykırı unsurlar taşıyan tekliflerin onaylanabilmesi için yöneticinin bu kural ihlalini kabul etmesi zorunludur.
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
                      Deterministik kural ihlalini ve olası riskleri inceledim. Bu teklif için istisna onayını onaylıyorum (acknowledged_policy_violation).
                    </span>
                  </label>
                </div>
              )}

              {/* Comment Field */}
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-text-muted block mb-1.5">
                  3. Yönetici Gerekçesi / Notu {reviewStatus === "rejected" || reviewStatus === "revision_requested" ? "(Zorunlu)" : "(Opsiyonel)"}
                </label>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={3}
                  placeholder="Onay, ret veya revizyon gerekçesini buraya yazabilirsiniz..."
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
              Vazgeç
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
                  ? "İşleniyor..."
                  : reviewStatus === "approved"
                  ? "Standart Onayla & PO Üret"
                  : reviewStatus === "exception_approved"
                  ? "İstisna Onayla & PO Üret"
                  : reviewStatus === "revision_requested"
                  ? "Revizyon Talep Et"
                  : "Teklifi Reddet"}
              </span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
