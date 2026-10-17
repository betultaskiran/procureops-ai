"use client";

import React, { useState } from "react";
import { 
  ShieldCheck, 
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
  Check
} from "lucide-react";
import { AnalysisResponse, Quote } from "@/lib/api/types";

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
          label: "Doğrulandı (Verified)",
          bg: "bg-emerald-500/15",
          border: "border-emerald-500/30",
          text: "text-emerald-400",
          dot: "bg-emerald-400",
        };
      case "failed":
      case "overridden":
        return {
          label: "Doğrulama Başarısız (Failed / Overridden)",
          bg: "bg-red-500/15",
          border: "border-red-500/30",
          text: "text-red-400",
          dot: "bg-red-400",
        };
      case "inconclusive":
        return {
          label: "Yetersiz Kanıt / Sonuçsuz (Inconclusive)",
          bg: "bg-amber-500/15",
          border: "border-amber-500/30",
          text: "text-amber-400",
          dot: "bg-amber-400",
        };
      case "exception_required":
        return {
          label: "İstisna Onayı Gerekiyor (Exception Required)",
          bg: "bg-red-500/15",
          border: "border-red-500/30",
          text: "text-red-400",
          dot: "bg-red-400",
        };
      default:
        return {
          label: "İnceleme Bekliyor (Pending)",
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
      name: "1. Doğrulama",
      fullName: "Girdi & Doküman Doğrulama",
      type: "Deterministik Python",
      status: "completed",
    },
    {
      name: "2. TCO & Kurallar",
      fullName: "TCO & Kesin Kurallar",
      type: "Deterministik Python",
      status: "completed",
    },
    {
      name: "3. Politika Uyumu",
      fullName: "Kurumsal RAG Analizi",
      type: "Qdrant RAG",
      status: analysis.evidence_items && analysis.evidence_items.length > 0 ? "completed" : "inconclusive",
    },
    {
      name: "4. LLM Önerisi",
      fullName: "Tedarikçi Öneri Ajanı",
      type: "LLM Danışman",
      status: recommendation ? "completed" : "pending",
    },
    {
      name: "5. Doğrulama",
      fullName: "Bağımsız Doğrulama Katmanı",
      type: "Doğrulama Motoru",
      status: recommendation?.verification_status?.toLowerCase() === "failed" || recommendation?.verification_status?.toLowerCase() === "overridden"
        ? "failed"
        : recommendation?.verification_status?.toLowerCase() === "inconclusive"
        ? "inconclusive"
        : "completed",
    },
    {
      name: "6. İnsan Onayı",
      fullName: "Yönetici İncelemesi & PO",
      type: "Human-in-the-Loop",
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
              6 Aşamalı Karar & Doğrulama Hattı (Pipeline Architecture)
            </h3>
          </div>
          <span className="text-[11px] text-text-muted">
            Deterministik kurallar, RAG ve LLM ayrımı
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
                Yapay Zeka Karar & Öneri Motoru
              </h2>
              <span className="text-xs text-text-muted">
                TCO optimizasyonu ve kurumsal politika uyumu değerlendirmesi
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

        {/* Highlighted Recommended Supplier */}
        {recommendedQuote ? (
          <div className="mb-5 p-4 rounded-xl bg-surface/70 border border-border flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-emerald-500/15 text-emerald-400 flex items-center justify-center font-bold border border-emerald-500/30">
                <Award size={20} />
              </div>
              <div>
                <span className="text-[11px] uppercase tracking-wider text-text-muted font-bold block">
                  ÖNERİLEN EN UYGUN TEDARİKÇİ
                </span>
                <span className="text-base font-bold text-text-primary">
                  {recommendedQuote.supplier_name || "Bilinmeyen Tedarikçi"}
                </span>
                <span className="text-xs text-text-muted block mt-0.5">
                  Toplam Fiyat: {new Intl.NumberFormat("tr-TR", { style: "currency", currency: recommendedQuote.currency || "TRY" }).format(recommendedQuote.total_price)}
                  {recommendedQuote.delivery_days ? ` • ${recommendedQuote.delivery_days} Gün Teslimat` : ""}
                  {recommendedQuote.warranty_months ? ` • ${recommendedQuote.warranty_months} Ay Garanti` : ""}
                </span>
              </div>
            </div>

            {onOpenReviewModal && (
              <button
                onClick={() => onOpenReviewModal(recommendedQuote.id)}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shadow-sm flex items-center gap-1.5 self-start sm:self-auto"
              >
                <CheckCircle size={14} />
                Öneriyi Değerlendir & Onayla
              </button>
            )}
          </div>
        ) : (
          <div className="mb-5 p-4 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300">
            Otomatik önerilen bir teklif belirlenmedi. Lütfen matristeki seçenekleri inceleyiniz.
          </div>
        )}

        {/* Reasoning Text */}
        <div className="mb-5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
            Karar Gerekçesi (LLM Reasoning)
          </h3>
          <div className="p-4 rounded-lg bg-surface/40 border border-border text-xs text-text-secondary leading-relaxed">
            {recommendation?.reasoning || "Gerekçe açıklaması oluşturulmadı."}
          </div>
        </div>

        {/* Risks & Verification Notes Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
          {recommendation?.risks && (
            <div className="p-4 rounded-lg bg-amber-500/5 border border-amber-500/20">
              <h4 className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                <AlertTriangle size={13} />
                Tespit Edilen Riskler & Uyarılar
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
                Alternatif Senaryolar & Notlar
              </h4>
              <p className="text-xs text-text-muted leading-relaxed">
                {recommendation.alternative_notes}
              </p>
            </div>
          )}
        </div>

        {recommendation?.verification_notes && (
          <div className="text-xs text-text-muted border-t border-border pt-3">
            <span className="font-semibold text-text-primary">Doğrulama Notu: </span>
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
                Dayanak Politika Maddeleri & Kanıtlar ({analysis.evidence_items.length})
              </h3>
            </div>
            <span className="text-xs text-text-muted">
              Kurumsal hafızadan getirilen RAG kanıtları
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {analysis.evidence_items.map((item, idx) => (
              <div
                key={idx}
                className="p-3.5 rounded-lg bg-surface/50 border border-border flex flex-col justify-between hover:border-primary/40 transition-colors"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">
                      {item.source_type}
                    </span>
                    <span className="text-[11px] font-mono text-text-muted">
                      {item.source_reference}
                    </span>
                  </div>
                  <p className="text-xs text-text-primary font-medium leading-relaxed mt-1">
                    &ldquo;{item.claim}&rdquo;
                  </p>
                </div>
              </div>
            ))}
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
                Deterministik Kural Kontrolleri (Hard-Rule Compliance)
              </h3>
              <span className="text-xs text-text-muted">
                Bütçe, teslimat, garanti ve ödeme kurallarının kesin matematiksel kontrolü
              </span>
            </div>
          </div>

          <button
            onClick={() => setIsRulesExpanded(!isRulesExpanded)}
            className="flex items-center gap-1 text-xs text-primary hover:underline font-medium"
          >
            {isRulesExpanded ? (
              <>
                <span>Detayları Daralt</span>
                <ChevronUp size={14} />
              </>
            ) : (
              <>
                <span>Tüm Kuralları İncele</span>
                <ChevronDown size={14} />
              </>
            )}
          </button>
        </div>

        {/* Safety Guardrail Notice */}
        <div className="p-3.5 rounded-lg bg-surface/60 border border-border text-xs text-text-muted leading-relaxed mb-4">
          <span className="font-semibold text-text-primary block mb-0.5">
            🔒 Değiştirilemez Politika Kuralı:
          </span>
          Deterministik kurallardan kalan veya ihlal eden teklifler, yapay zeka tarafından önerilse dahi standart onayla ilerletilemez. Yönetici tarafından bilinçli bir &ldquo;İstisna Onayı&rdquo; verilmesi ve kural ihlalinin açıkça teyit edilmesi zorunludur.
        </div>

        {isRulesExpanded && (
          <div className="space-y-4 pt-2">
            {checksByQuote.map(({ quote, checks }) => (
              <div key={quote.id} className="border border-border rounded-lg overflow-hidden bg-surface/30">
                <div className="p-3 bg-surface/60 border-b border-border flex items-center justify-between">
                  <span className="text-xs font-bold text-text-primary">
                    {quote.supplier_name || "Bilinmeyen Tedarikçi"}
                  </span>
                  <span className="text-[11px] text-text-muted">
                    {checks.length} Kural Denetlendi
                  </span>
                </div>

                <div className="divide-y divide-border">
                  {checks.length === 0 ? (
                    <div className="p-3 text-xs text-text-muted">Kural kaydı bulunamadı.</div>
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
                              <span>Gerçekleşen: <strong className="text-text-primary">{check.actual_value}</strong></span>
                              <span>•</span>
                              <span>Beklenen Kural: <strong className="text-text-primary">{check.required_value}</strong></span>
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
