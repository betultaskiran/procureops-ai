"use client";

import React from "react";
import { 
  CheckCircle, 
  AlertTriangle, 
  XCircle, 
  Award, 
  HelpCircle, 
  ShieldAlert, 
  ArrowRight,
  TrendingUp,
  FileText,
  Clock
} from "lucide-react";
import { Quote, RFQ, AnalysisResponse } from "@/lib/api/types";

interface ComparisonMatrixProps {
  quotes: Quote[];
  rfq: RFQ;
  analysis: AnalysisResponse | null;
  selectedQuoteId: string | null;
  onSelectQuote: (quoteId: string) => void;
  onOpenReviewModal?: (quoteId?: string) => void;
  onOpenSupplierDrawer?: (supplierId: string, supplierName: string) => void;
}

export const ComparisonMatrix: React.FC<ComparisonMatrixProps> = ({
  quotes,
  rfq,
  analysis,
  selectedQuoteId,
  onSelectQuote,
  onOpenReviewModal,
  onOpenSupplierDrawer,
}) => {
  if (!quotes || quotes.length === 0) {
    return null;
  }

  // Format currency helper
  const formatCurrency = (amount: number | null | undefined, currency: string = "TRY") => {
    if (amount === null || amount === undefined) return "-";
    try {
      return new Intl.NumberFormat("tr-TR", {
        style: "currency",
        currency: currency || "TRY",
        maximumFractionDigits: 2,
      }).format(amount);
    } catch {
      return `${amount.toLocaleString("tr-TR")} ${currency}`;
    }
  };

  // Currency mismatch detection
  const distinctCurrencies = Array.from(
    new Set(quotes.map((q) => q.currency).filter(Boolean))
  );
  const hasCurrencyMismatch = distinctCurrencies.length > 1;

  const recommendedQuoteId = analysis?.recommendation?.recommended_quote_id;

  // Helper for compliance status per quote
  const getComplianceStatus = (quote: Quote) => {
    const checks = analysis?.compliance_checks?.filter((c) => c.quote_id === quote.id) || [];
    const hasFail = quote.is_compliant === false || checks.some((c) => c.result === "fail");
    const hasWarning = checks.some((c) => c.result === "warning");

    if (hasFail) {
      const failChecks = checks.filter((c) => c.result === "fail");
      return {
        status: "fail",
        label: "Kural İhlali",
        subtext: failChecks.length > 0 ? failChecks.map((c) => c.rule_description).join(", ") : "Politika kurallarına uymuyor",
        bg: "bg-red-500/10",
        border: "border-red-500/30",
        text: "text-red-400",
        icon: <XCircle size={14} className="text-red-400 shrink-0" />,
      };
    }

    if (hasWarning) {
      return {
        status: "warning",
        label: "İnceleme Gerekli",
        subtext: "Hafif uyarı veya sınırda değer",
        bg: "bg-amber-500/10",
        border: "border-amber-500/30",
        text: "text-amber-400",
        icon: <AlertTriangle size={14} className="text-amber-400 shrink-0" />,
      };
    }

    if (quote.is_compliant === true || (checks.length > 0 && checks.every((c) => c.result === "pass"))) {
      return {
        status: "pass",
        label: "Politikaya Uygun",
        subtext: "Tüm deterministik kuralları geçti",
        bg: "bg-emerald-500/10",
        border: "border-emerald-500/30",
        text: "text-emerald-400",
        icon: <CheckCircle size={14} className="text-emerald-400 shrink-0" />,
      };
    }

    return {
      status: "unknown",
      label: "İncelenmedi",
      subtext: "Henüz analiz çalıştırılmadı",
      bg: "bg-zinc-800",
      border: "border-zinc-700",
      text: "text-zinc-400",
      icon: <HelpCircle size={14} className="text-zinc-400 shrink-0" />,
    };
  };

  return (
    <div className="bg-surface-elevated border border-border rounded-xl shadow-sm overflow-hidden flex flex-col">
      {/* Header */}
      <div className="p-5 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-surface/40">
        <div>
          <div className="flex items-center gap-2">
            <TrendingUp size={18} className="text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-text-primary">
              Çoklu Teklif Karşılaştırma Matrisi (Multi-Quote Matrix)
            </h2>
          </div>
          <p className="text-xs text-text-muted mt-1">
            Bu RFQ için sunulan {quotes.length} tedarikçi teklifinin finansal ve operasyonel kriterler bazında yan yana karşılaştırması
          </p>
        </div>

        {/* Currency or Eligible Count Pill */}
        <div className="flex items-center gap-2">
          <span className="text-xs px-2.5 py-1 rounded-full bg-surface border border-border font-medium text-text-muted">
            {quotes.length} Teklif İnceleniyor
          </span>
        </div>
      </div>

      {/* Currency Mismatch Warning Banner */}
      {hasCurrencyMismatch && (
        <div className="p-4 bg-amber-500/10 border-b border-amber-500/30 text-amber-300 text-xs flex items-start gap-2.5">
          <ShieldAlert size={16} className="text-amber-400 shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            <span className="font-semibold block text-amber-200 mb-0.5">
              Farklı Para Birimi Uyarısı (Cross-Currency Mismatch)
            </span>
            Teklifler birden fazla para biriminde ({distinctCurrencies.join(", ")}) sunulmuştur. Döviz kuru çevrimi yapılmadan TCO ve fiyat karşılaştırması doğrudan sıralanamaz. Karşılaştırma yaparken para birimlerine dikkat ediniz.
          </div>
        </div>
      )}

      {/* Comparison Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-border bg-surface/60">
              <th className="p-4 font-semibold text-text-muted uppercase tracking-wider w-48 min-w-[190px] sticky left-0 bg-surface/90 backdrop-blur z-10 border-r border-border">
                Karşılaştırma Kriteri
              </th>
              {quotes.map((q) => {
                const isRecommended = q.id === recommendedQuoteId;
                const isSelected = q.id === selectedQuoteId;

                return (
                  <th
                    key={q.id}
                    className={`p-4 min-w-[240px] align-top transition-colors border-r border-border last:border-r-0 ${
                      isRecommended
                        ? "bg-primary/5"
                        : isSelected
                        ? "bg-surface-elevated"
                        : ""
                    }`}
                  >
                    <div className="flex flex-col gap-1.5">
                      {isRecommended && (
                        <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 w-fit">
                          <Award size={12} className="text-emerald-400" />
                          Yapay Zeka Önerisi
                        </div>
                      )}
                      
                      <div className="font-semibold text-sm text-text-primary leading-tight">
                        {q.supplier_name || "Bilinmeyen Tedarikçi"}
                      </div>

                      {q.extracted_supplier_name &&
                        q.extracted_supplier_name.toLowerCase() !==
                          (q.supplier_name || "").toLowerCase() && (
                          <div className="text-[11px] text-amber-400 font-normal">
                            Belgeden: {q.extracted_supplier_name}
                          </div>
                      )}

                      <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                        <button
                          onClick={() => onSelectQuote(q.id)}
                          className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
                            isSelected
                              ? "bg-primary text-white shadow-sm"
                              : "bg-surface border border-border text-text-muted hover:text-text-primary hover:bg-bg"
                          }`}
                        >
                          {isSelected ? "İnceleniyor" : "Detayı Seç"}
                        </button>

                        {onOpenReviewModal && (
                          <button
                            onClick={() => onOpenReviewModal(q.id)}
                            className="px-2.5 py-1 rounded text-[11px] font-medium bg-emerald-600/80 hover:bg-emerald-600 text-white transition-colors"
                          >
                            Karar Ver
                          </button>
                        )}

                        {onOpenSupplierDrawer && (
                          <button
                            type="button"
                            onClick={() => onOpenSupplierDrawer(q.supplier_id, q.supplier_name || "Tedarikçi")}
                            className="px-2 py-1 rounded text-[11px] font-medium bg-surface border border-border text-text-secondary hover:text-text-primary hover:border-primary/50 transition-colors flex items-center gap-1"
                            title="Tedarikçi teslimat güvenilirliği ve geçmiş sipariş karnesini aç"
                          >
                            <Clock size={11} className="text-primary" />
                            <span>Karne</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>

          <tbody className="divide-y divide-border">
            {/* 1. Uyum Durumu (Compliance Status) */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 font-medium text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                Politika ve Kural Uyumu
              </td>
              {quotes.map((q) => {
                const comp = getComplianceStatus(q);
                return (
                  <td key={q.id} className="p-3.5 border-r border-border last:border-r-0 align-top">
                    <div className="flex flex-col gap-1">
                      <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-semibold ${comp.bg} ${comp.border} ${comp.text} border w-fit`}>
                        {comp.icon}
                        <span>{comp.label}</span>
                      </div>
                      <span className="text-[11px] text-text-muted">{comp.subtext}</span>
                    </div>
                  </td>
                );
              })}
            </tr>

            {/* 1.5 Tedarikçi Geçmişi & Performans Karnesi */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 font-medium text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                <div className="text-text-primary font-medium">Tedarikçi Geçmiş Karnesi</div>
                <div className="text-[10px] text-text-muted font-normal">Sipariş & teslimat güvenilirliği</div>
              </td>
              {quotes.map((q) => (
                <td key={q.id} className="p-3.5 border-r border-border last:border-r-0 align-top">
                  {onOpenSupplierDrawer ? (
                    <button
                      type="button"
                      onClick={() => onOpenSupplierDrawer(q.supplier_id, q.supplier_name || "Tedarikçi")}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-surface/60 hover:bg-surface border border-border hover:border-primary/40 text-text-primary transition-all text-left group"
                    >
                      <Clock size={13} className="text-primary shrink-0 group-hover:scale-110 transition-transform" />
                      <span>Geçmişi İncele →</span>
                    </button>
                  ) : (
                    <span className="text-text-muted text-xs">-</span>
                  )}
                </td>
              ))}
            </tr>

            {/* 2. Toplam TCO (Total Cost of Ownership) */}
            <tr className="bg-primary/5 hover:bg-primary/10 transition-colors font-medium">
              <td className="p-3.5 text-text-primary sticky left-0 bg-surface/95 backdrop-blur border-r border-border">
                <div className="font-semibold text-primary">Hesaplanan Toplam TCO</div>
                <div className="text-[10px] text-text-muted font-normal">Tüm maliyet kalemleri dahil</div>
              </td>
              {quotes.map((q) => {
                const tco = analysis?.tco_results?.find((t) => t.quote_id === q.id);
                const isIncomplete = q.vat_rate === null || q.shipping_cost === null;

                return (
                  <td key={q.id} className="p-3.5 border-r border-border last:border-r-0 align-top">
                    <div className="text-sm font-bold text-text-primary">
                      {tco ? formatCurrency(tco.total_tco, tco.currency) : formatCurrency(q.total_price, q.currency)}
                    </div>
                    {isIncomplete ? (
                      <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                        ⚠️ Eksik Kalem / TCO Tahmini
                      </span>
                    ) : (
                      <span className="inline-block mt-1 text-[10px] text-emerald-400">
                        Tam Maliyet Onaylı
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>

            {/* 3. Birim / Ara Toplam (Subtotal) */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                Ara Toplam (KDV Hariç)
              </td>
              {quotes.map((q) => (
                <td key={q.id} className="p-3.5 border-r border-border last:border-r-0 text-text-primary font-medium">
                  {formatCurrency(q.subtotal, q.currency)}
                </td>
              ))}
            </tr>

            {/* 4. KDV Oranı & Tutarı (VAT) - CRITICAL ZERO VS NULL */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                KDV Oranı ve Tutarı
              </td>
              {quotes.map((q) => {
                const isZeroConfirmed = q.vat_rate === 0 && (q.vat_amount === 0 || q.vat_amount === null);
                const isNull = q.vat_rate === null || q.vat_amount === null;

                return (
                  <td key={q.id} className="p-3.5 border-r border-border last:border-r-0">
                    {isZeroConfirmed ? (
                      <div className="flex flex-col">
                        <span className="text-emerald-400 font-semibold">%0 (0,00 {q.currency})</span>
                        <span className="text-[10px] text-emerald-500/80">KDV Muafiyeti / %0 Onaylı</span>
                      </div>
                    ) : isNull ? (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 font-medium">
                        <AlertTriangle size={11} />
                        [Eksik Veri / İnceleme Gerekli]
                      </span>
                    ) : (
                      <div className="flex flex-col">
                        <span className="text-text-primary font-medium">
                          %{Math.round((q.vat_rate || 0) * 100)} ({formatCurrency(q.vat_amount, q.currency)})
                        </span>
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>

            {/* 5. Kargo / Lojistik Maliyeti - CRITICAL ZERO VS NULL */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                Kargo ve Lojistik
              </td>
              {quotes.map((q) => {
                const isFreeConfirmed = q.shipping_cost === 0;
                const isNull = q.shipping_cost === null;

                return (
                  <td key={q.id} className="p-3.5 border-r border-border last:border-r-0">
                    {isFreeConfirmed ? (
                      <span className="text-emerald-400 font-semibold">
                        0,00 {q.currency} (Ücretsiz / Dahil)
                      </span>
                    ) : isNull ? (
                      <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 font-medium">
                        <AlertTriangle size={11} />
                        [Belirtilmemiş / Hariç Olabilir]
                      </span>
                    ) : (
                      <span className="text-text-primary font-medium">
                        {formatCurrency(q.shipping_cost, q.currency)}
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>

            {/* 6. İskonto & Diğer Maliyetler */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                İskonto / Diğer Maliyetler
              </td>
              {quotes.map((q) => {
                const hasDiscount = (q.discount_amount || 0) > 0;
                const hasOther = (q.other_costs || 0) > 0;

                return (
                  <td key={q.id} className="p-3.5 border-r border-border last:border-r-0 text-text-secondary">
                    {hasDiscount && (
                      <div className="text-emerald-400">
                        İskonto: -{formatCurrency(q.discount_amount, q.currency)}
                      </div>
                    )}
                    {hasOther && (
                      <div className="text-amber-400">
                        Diğer: +{formatCurrency(q.other_costs, q.currency)}
                      </div>
                    )}
                    {!hasDiscount && !hasOther && <span>-</span>}
                  </td>
                );
              })}
            </tr>

            {/* 7. Teslimat Süresi (Delivery) */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                <div>Teslimat Süresi</div>
                {rfq.max_delivery_days && (
                  <div className="text-[10px] text-text-muted">RFQ Limiti: Maks {rfq.max_delivery_days} Gün</div>
                )}
              </td>
              {quotes.map((q) => {
                const isOver = rfq.max_delivery_days && q.delivery_days && q.delivery_days > rfq.max_delivery_days;
                return (
                  <td key={q.id} className="p-3.5 border-r border-border last:border-r-0">
                    <span className={`font-medium ${isOver ? "text-red-400" : "text-text-primary"}`}>
                      {q.delivery_days ? `${q.delivery_days} Gün` : "Belirtilmemiş"}
                    </span>
                    {isOver && (
                      <span className="block text-[10px] text-red-400 font-semibold mt-0.5">
                        ⚠️ Limit Aşıldı (&gt; {rfq.max_delivery_days} gün)
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>

            {/* 8. Garanti Süresi (Warranty) */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                <div>Garanti Süresi</div>
                {rfq.min_warranty_months && (
                  <div className="text-[10px] text-text-muted">RFQ Şartı: Min {rfq.min_warranty_months} Ay</div>
                )}
              </td>
              {quotes.map((q) => {
                const isUnder = rfq.min_warranty_months && q.warranty_months && q.warranty_months < rfq.min_warranty_months;
                return (
                  <td key={q.id} className="p-3.5 border-r border-border last:border-r-0">
                    <span className={`font-medium ${isUnder ? "text-red-400" : "text-text-primary"}`}>
                      {q.warranty_months ? `${q.warranty_months} Ay` : "Belirtilmemiş"}
                    </span>
                    {isUnder && (
                      <span className="block text-[10px] text-red-400 font-semibold mt-0.5">
                        ⚠️ Yetersiz Garanti (&lt; {rfq.min_warranty_months} ay)
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>

            {/* 9. Ödeme Koşulları (Payment Terms) */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                <div>Ödeme Koşulları</div>
                {rfq.payment_terms && (
                  <div className="text-[10px] text-text-muted">RFQ Koşulu: {rfq.payment_terms}</div>
                )}
              </td>
              {quotes.map((q) => (
                <td key={q.id} className="p-3.5 border-r border-border last:border-r-0 text-text-primary font-medium">
                  {q.payment_terms || "Belirtilmemiş"}
                </td>
              ))}
            </tr>

            {/* 10. Çıkarma Güven Skoru (Extraction Confidence) */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                OCR / Çıkarma Güveni
              </td>
              {quotes.map((q) => {
                const conf = q.extraction_confidence !== null ? Math.round(q.extraction_confidence * 100) : null;
                const confColor =
                  conf === null
                    ? "text-zinc-500"
                    : conf >= 85
                    ? "text-emerald-400"
                    : conf >= 70
                    ? "text-amber-400"
                    : "text-red-400";

                return (
                  <td key={q.id} className="p-3.5 border-r border-border last:border-r-0">
                    {conf !== null ? (
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-surface rounded-full overflow-hidden border border-border">
                          <div
                            className={`h-full ${
                              conf >= 85
                                ? "bg-emerald-500"
                                : conf >= 70
                                ? "bg-amber-500"
                                : "bg-red-500"
                            }`}
                            style={{ width: `${conf}%` }}
                          />
                        </div>
                        <span className={`font-mono text-xs font-semibold ${confColor}`}>
                          %{conf}
                        </span>
                      </div>
                    ) : (
                      <span className="text-zinc-500">N/A</span>
                    )}
                  </td>
                );
              })}
            </tr>

            {/* 11. Kalem Sayısı (Items) */}
            <tr className="hover:bg-surface/30">
              <td className="p-3.5 text-text-muted sticky left-0 bg-surface/90 backdrop-blur border-r border-border">
                Kalem Sayısı
              </td>
              {quotes.map((q) => (
                <td key={q.id} className="p-3.5 border-r border-border last:border-r-0 text-text-secondary">
                  <div className="flex items-center gap-1.5">
                    <FileText size={13} className="text-primary" />
                    <span>{q.items?.length || 0} Kalem</span>
                  </div>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};
