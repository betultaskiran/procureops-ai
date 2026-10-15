"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { 
  X, 
  Clock, 
  ShieldCheck, 
  AlertTriangle, 
  CheckCircle, 
  XCircle, 
  Building, 
  TrendingUp, 
  DollarSign, 
  Package, 
  FileText, 
  ChevronLeft, 
  ChevronRight, 
  Loader2, 
  HelpCircle, 
  AlertCircle,
  ExternalLink,
  ShieldAlert,
  RotateCcw
} from "lucide-react";
import { 
  SupplierPerformanceResponse, 
  PaginatedSupplierHistoryResponse,
  SupplierHistoryItemResponse
} from "@/lib/api/types";
import { suppliersApi } from "@/lib/api/suppliers";

interface SupplierPerformanceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  supplierId: string;
  supplierName: string;
}

export const SupplierPerformanceDrawer: React.FC<SupplierPerformanceDrawerProps> = ({
  isOpen,
  onClose,
  supplierId,
  supplierName,
}) => {
  // Performance state
  const [performance, setPerformance] = useState<SupplierPerformanceResponse | null>(null);
  const [performanceLoading, setPerformanceLoading] = useState(false);
  const [performanceError, setPerformanceError] = useState<string | null>(null);

  // History state
  const [history, setHistory] = useState<PaginatedSupplierHistoryResponse | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);

  // Accessibility and DOM refs
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  // Active request controller ref to abort inflight requests
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentSupplierIdRef = useRef(supplierId);

  useEffect(() => {
    currentSupplierIdRef.current = supplierId;
  }, [supplierId]);

  // Reset all states and abort inflight requests
  const resetAllState = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setPerformance(null);
    setPerformanceLoading(false);
    setPerformanceError(null);
    setHistory(null);
    setHistoryLoading(false);
    setHistoryError(null);
    setHistoryPage(1);
  }, []);

  // Fetch performance intelligence independently with request identity guard
  const fetchPerformance = useCallback(async (id: string, signal?: AbortSignal) => {
    if (!id) return;
    try {
      setPerformanceLoading(true);
      setPerformanceError(null);
      const data = await suppliersApi.getPerformance(id, signal);
      // Guard against stale responses from previous suppliers or closed drawer
      if (currentSupplierIdRef.current === id && data.supplier_id === id) {
        setPerformance(data);
      }
    } catch (err: any) {
      if (err.name !== "AbortError" && currentSupplierIdRef.current === id) {
        setPerformanceError(err.message || "Tedarikçi performans verileri alınamadı.");
      }
    } finally {
      if (currentSupplierIdRef.current === id) {
        setPerformanceLoading(false);
      }
    }
  }, []);

  // Fetch paginated history independently with request identity guard
  const fetchHistory = useCallback(async (id: string, page: number, signal?: AbortSignal) => {
    if (!id) return;
    try {
      setHistoryLoading(true);
      setHistoryError(null);
      const data = await suppliersApi.getHistory(id, page, 20, signal);
      if (currentSupplierIdRef.current === id) {
        setHistory(data);
      }
    } catch (err: any) {
      if (err.name !== "AbortError" && currentSupplierIdRef.current === id) {
        setHistoryError(err.message || "Tedarikçi sipariş geçmişi alınamadı.");
      }
    } finally {
      if (currentSupplierIdRef.current === id) {
        setHistoryLoading(false);
      }
    }
  }, []);

  // Main lifecycle: trigger fetches when drawer is opened or supplierId changes
  useEffect(() => {
    if (!isOpen || !supplierId) {
      resetAllState();
      return;
    }

    // Abort any previous inflight fetches
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Reset data immediately to prevent stale UI flash
    setPerformance(null);
    setHistory(null);
    setHistoryPage(1);

    fetchPerformance(supplierId, controller.signal);
    fetchHistory(supplierId, 1, controller.signal);

    return () => {
      controller.abort();
    };
  }, [isOpen, supplierId, fetchPerformance, fetchHistory, resetAllState]);

  // Retry handlers with dedicated AbortController
  const handleRetryPerformance = () => {
    if (!supplierId) return;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    fetchPerformance(supplierId, controller.signal);
  };

  const handleRetryHistory = () => {
    if (!supplierId) return;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    fetchHistory(supplierId, historyPage, controller.signal);
  };

  // Page change handler for history table
  const handlePageChange = (newPage: number) => {
    if (!supplierId || newPage === historyPage) return;
    setHistoryPage(newPage);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    fetchHistory(supplierId, newPage, controller.signal);
  };

  // Accessibility: Focus management, body scroll lock, Escape key and focus trapping
  useEffect(() => {
    if (isOpen) {
      previousActiveElement.current = document.activeElement as HTMLElement;
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";

      // Set initial focus
      const timer = setTimeout(() => {
        closeButtonRef.current?.focus();
      }, 50);

      return () => {
        clearTimeout(timer);
        document.body.style.overflow = originalOverflow;
        previousActiveElement.current?.focus?.();
      };
    }
  }, [isOpen]);

  // Keyboard trap and Escape key listener
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === "Tab" && drawerRef.current) {
        const focusableElements = drawerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Format currency helper
  const formatCurrency = (amount: number | string | null | undefined, currency: string = "TRY") => {
    if (amount === null || amount === undefined) return "-";
    const num = typeof amount === "string" ? parseFloat(amount) : amount;
    if (isNaN(num)) return "-";
    try {
      return new Intl.NumberFormat("tr-TR", {
        style: "currency",
        currency: currency || "TRY",
        maximumFractionDigits: 2,
      }).format(num);
    } catch {
      return `${num.toLocaleString("tr-TR")} ${currency}`;
    }
  };

  // Format date helper
  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return "-";
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString("tr-TR", { year: "numeric", month: "short", day: "numeric" });
    } catch {
      return dateStr;
    }
  };

  // Format delay days helper
  const renderDelayBadge = (delayDays: number | null | undefined) => {
    if (delayDays === null || delayDays === undefined) {
      return <span className="text-text-muted">-</span>;
    }
    if (delayDays < 0) {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-medium">
          {Math.abs(delayDays)} gün erken
        </span>
      );
    }
    if (delayDays === 0) {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-medium">
          Zamanında (0 gün)
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-red-500/15 text-red-400 border border-red-500/30 font-medium">
        +{delayDays} gün gecikme
      </span>
    );
  };

  // Safe pagination calculations
  const totalCount = history?.total_count || 0;
  const totalPages = Math.max(0, history?.total_pages || 0);
  const currentPage = totalPages === 0 ? 0 : historyPage;

  return (
    <div 
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity duration-300 animate-in fade-in"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="supplier-drawer-title"
        aria-describedby="supplier-drawer-subtitle"
        className="w-full max-w-3xl bg-surface-elevated border-l border-border h-full shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-300"
      >
        {/* ── Drawer Header ────────────────────────────────────────────── */}
        <div className="p-5 border-b border-border bg-surface/70 flex items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0">
              <Building size={20} />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 id="supplier-drawer-title" className="text-base font-bold text-text-primary truncate">
                  {supplierName || performance?.supplier_name || "Tedarikçi Performansı"}
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded bg-surface border border-border text-text-muted font-mono shrink-0">
                  ID: {supplierId ? `${supplierId.substring(0, 8)}...` : "-"}
                </span>
              </div>
              <p id="supplier-drawer-subtitle" className="text-xs text-text-muted mt-0.5 truncate">
                Tedarikçi teslimat güvenilirliği, finansal işlem hacmi ve sipariş geçmişi karnesi
              </p>
            </div>
          </div>

          <button
            ref={closeButtonRef}
            onClick={onClose}
            className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface border border-transparent hover:border-border transition-colors shrink-0"
            aria-label="Kapat"
          >
            <X size={18} />
          </button>
        </div>

        {/* ── Drawer Scrollable Body ──────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* Conflict / Collision Banner */}
          {performance?.has_conflicts && (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-3">
              <ShieldAlert size={18} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <span className="font-bold block text-amber-200">
                  Veri Çakışması / Mükerrer Kayıt Uyarısı (Data Collision Warning)
                </span>
                <p className="text-text-muted leading-relaxed">
                  {performance.conflict_notes || "Bu tedarikçiye ait harici ERP geçmiş kayıtları ile platform Satın Alma Siparişleri (PO) arasında mükerrer referanslar tespit edilmiştir. Metriklerin çift sayılmasını önlemek için ilgili kayıtlar filtrelenmiş ve aşağıdaki tabloda işaretlenmiştir."}
                </p>
              </div>
            </div>
          )}

          {/* ── SECTION 1: Performance Intelligence KPI Cards ────────── */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted flex items-center gap-1.5">
                <TrendingUp size={14} className="text-primary" />
                Performans ve Güvenilirlik Özeti
              </h3>
              {performanceLoading && (
                <span className="flex items-center gap-1.5 text-xs text-text-muted">
                  <Loader2 size={12} className="animate-spin text-primary" />
                  Yükleniyor...
                </span>
              )}
            </div>

            {performanceError ? (
              <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-xs text-red-300 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <AlertCircle size={16} className="text-red-400 shrink-0" />
                  <span>{performanceError}</span>
                </div>
                <button
                  onClick={handleRetryPerformance}
                  className="px-2.5 py-1 rounded bg-red-600 hover:bg-red-500 text-white text-[11px] font-medium transition-colors flex items-center gap-1"
                >
                  <RotateCcw size={11} /> Tekrar Dene
                </button>
              </div>
            ) : performanceLoading && !performance ? (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="h-28 rounded-xl bg-surface/50 border border-border animate-pulse" />
                <div className="h-28 rounded-xl bg-surface/50 border border-border animate-pulse" />
                <div className="h-28 rounded-xl bg-surface/50 border border-border animate-pulse" />
              </div>
            ) : performance ? (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {/* 1.1 Delivery Reliability KPI */}
                <div className="p-4 rounded-xl bg-surface/60 border border-border flex flex-col justify-between">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-text-muted font-medium">Teslimat Güvenilirliği</span>
                    <Clock size={16} className="text-primary" />
                  </div>

                  <div className="my-2">
                    {performance.delivery_reliability.is_available && performance.delivery_reliability.on_time_percentage !== null ? (
                      <div>
                        <div className="text-2xl font-bold text-text-primary tracking-tight">
                          %{performance.delivery_reliability.on_time_percentage.toFixed(1)}
                        </div>
                        <div className="text-[11px] text-text-muted mt-0.5">
                          {performance.delivery_reliability.on_time_orders_count ?? 0} / {performance.delivery_reliability.eligible_orders_count} sipariş zamanında
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div className="text-sm font-semibold text-text-muted">
                          Veri Yok
                        </div>
                        <div className="text-[11px] text-text-muted mt-0.5">
                          {performance.delivery_reliability.notes || "Henüz teslimat tarihi verisi bulunmuyor."}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Confidence Badge */}
                  <div className="pt-2 border-t border-border/60 flex items-center justify-between text-[11px]">
                    <span className="text-text-muted">Örneklem Güveni:</span>
                    <span className={`px-2 py-0.5 rounded font-semibold ${
                      performance.delivery_reliability.confidence === "high"
                        ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                        : performance.delivery_reliability.confidence === "low"
                        ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                        : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                    }`}>
                      {performance.delivery_reliability.confidence === "high"
                        ? "Yüksek (5+ Sipariş)"
                        : performance.delivery_reliability.confidence === "low"
                        ? "Sınırlı (2–4 Sipariş)"
                        : "Yetersiz (< 2 Sipariş)"}
                    </span>
                  </div>
                </div>

                {/* 1.2 Average Delay KPI */}
                <div className="p-4 rounded-xl bg-surface/60 border border-border flex flex-col justify-between">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-text-muted font-medium">Ortalama Gecikme</span>
                    <Package size={16} className="text-primary" />
                  </div>

                  <div className="my-2">
                    {performance.delivery_reliability.is_available && performance.delivery_reliability.average_delay_days !== null ? (
                      <div>
                        <div className={`text-2xl font-bold tracking-tight ${
                          performance.delivery_reliability.average_delay_days <= 0
                            ? "text-emerald-400"
                            : "text-red-400"
                        }`}>
                          {performance.delivery_reliability.average_delay_days > 0 ? "+" : ""}
                          {performance.delivery_reliability.average_delay_days.toFixed(1)} Gün
                        </div>
                        <div className="text-[11px] text-text-muted mt-0.5">
                          {performance.delivery_reliability.early_orders_count ?? 0} erken, {performance.delivery_reliability.late_orders_count ?? 0} geciken sipariş
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div className="text-sm font-semibold text-text-muted">-</div>
                        <div className="text-[11px] text-text-muted mt-0.5">Hesaplanabilir teslimat kaydı yok</div>
                      </div>
                    )}
                  </div>

                  <div className="pt-2 border-t border-border/60 text-[11px] text-text-muted flex justify-between">
                    <span>Erken Teslimatlar:</span>
                    <span className="font-semibold text-emerald-400">
                      {performance.delivery_reliability.early_orders_count ?? 0} Adet
                    </span>
                  </div>
                </div>

                {/* 1.3 Quality Tracking KPI */}
                <div className="p-4 rounded-xl bg-surface/60 border border-border flex flex-col justify-between">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-text-muted font-medium">Kalite ve Kusur Kaydı</span>
                    <ShieldCheck size={16} className="text-primary" />
                  </div>

                  <div className="my-2">
                    {performance.quality_metrics.is_tracked ? (
                      <div>
                        <div className={`text-2xl font-bold tracking-tight ${
                          (performance.quality_metrics.total_quality_issues || 0) === 0
                            ? "text-emerald-400"
                            : "text-amber-400"
                        }`}>
                          {performance.quality_metrics.total_quality_issues || 0} Kusur
                        </div>
                        <div className="text-[11px] text-text-muted mt-0.5">
                          {performance.quality_metrics.total_rejections || 0} adet ürün/parti iade edildi
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div className="text-sm font-semibold text-text-muted">
                          Takip Edilmiyor
                        </div>
                        <div className="text-[11px] text-text-muted mt-0.5">
                          Bu tedarikçi için kayıtlı hata veya ret bilgisi bulunmuyor.
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="pt-2 border-t border-border/60 text-[11px] text-text-muted flex justify-between">
                    <span>Kapsam:</span>
                    <span className="font-semibold text-text-primary">
                      {performance.quality_metrics.tracked_orders_count} Sipariş İncelendi
                    </span>
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          {/* ── SECTION 2: Order Status Distribution ──────────────────── */}
          {performance && (
            <div className="p-4 rounded-xl bg-surface/40 border border-border space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Sipariş Durumu Dağılımı ({performance.order_summary.total_orders_count} Toplam Kayıt)
                </span>
                <span className="text-[11px] text-text-muted">
                  Değerlendirilen: {performance.evaluated_orders_count} (Taslaklar Hariç)
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                <div className="p-2.5 rounded-lg bg-surface border border-border">
                  <div className="text-text-muted text-[11px]">Tamamlanan</div>
                  <div className="text-base font-bold text-emerald-400 mt-0.5">
                    {performance.order_summary.completed_orders_count}
                  </div>
                </div>
                <div className="p-2.5 rounded-lg bg-surface border border-border">
                  <div className="text-text-muted text-[11px]">Teslim Edilen</div>
                  <div className="text-base font-bold text-blue-400 mt-0.5">
                    {performance.order_summary.delivered_orders_count}
                  </div>
                </div>
                <div className="p-2.5 rounded-lg bg-surface border border-border">
                  <div className="text-text-muted text-[11px]">Aktif / Yolda</div>
                  <div className="text-base font-bold text-amber-400 mt-0.5">
                    {performance.order_summary.active_orders_count}
                  </div>
                </div>
                <div className="p-2.5 rounded-lg bg-surface border border-border">
                  <div className="text-text-muted text-[11px]">İptal / İhtilaf</div>
                  <div className="text-base font-bold text-red-400 mt-0.5">
                    {performance.order_summary.cancelled_orders_count}
                  </div>
                </div>
                <div className="p-2.5 rounded-lg bg-surface border border-border">
                  <div className="text-text-muted text-[11px]">Taslak (Muaf)</div>
                  <div className="text-base font-bold text-zinc-400 mt-0.5">
                    {performance.order_summary.draft_orders_count}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── SECTION 3: Financial Summary By Currency ──────────────── */}
          {performance && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted flex items-center gap-1.5">
                <DollarSign size={14} className="text-primary" />
                Finansal İşlem Hacmi (Para Birimi Bazında İzole)
              </h3>

              {Object.keys(performance.financial_summary).length === 0 ? (
                <div className="p-4 rounded-xl bg-surface/30 border border-border text-center text-xs text-text-muted">
                  Bu tedarikçi için kayıtlı finansal işlem bulunamadı.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Object.entries(performance.financial_summary).map(([currency, fin]) => (
                    <div key={currency} className="p-4 rounded-xl bg-surface/50 border border-border space-y-3">
                      <div className="flex items-center justify-between border-b border-border/60 pb-2">
                        <span className="text-xs font-bold px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">
                          {currency}
                        </span>
                        <span className="text-xs text-text-muted font-medium">
                          {fin.orders_count} Sipariş
                        </span>
                      </div>

                      <div className="space-y-1.5 text-xs">
                        <div className="flex justify-between items-baseline">
                          <span className="text-text-muted">Toplam Harcama:</span>
                          <span className="font-bold text-sm text-text-primary">
                            {formatCurrency(fin.total_spend, currency)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">Ortalama Sipariş Tutarı:</span>
                          <span className="font-medium text-text-secondary">
                            {formatCurrency(fin.average_order_value, currency)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">Min / Maks Aralık:</span>
                          <span className="text-text-secondary">
                            {formatCurrency(fin.min_order_value, currency)} — {formatCurrency(fin.max_order_value, currency)}
                          </span>
                        </div>
                      </div>

                      <div className="pt-2 border-t border-border/60 text-[10px] text-text-muted flex items-center justify-between">
                        <span>Veri Güvenilirliği:</span>
                        <span className="font-medium text-text-primary">
                          {fin.final_amount_orders_count} Kesinleşmiş PO | {fin.quoted_amount_orders_count} Teklif
                          {fin.historical_amount_orders_count > 0 ? ` | ${fin.historical_amount_orders_count} Harici` : ""}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── SECTION 4: Paginated Order History Table ──────────────── */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted flex items-center gap-1.5">
                <FileText size={14} className="text-primary" />
                Sipariş ve Teslimat Geçmişi Kayıtları
              </h3>
              {historyLoading && (
                <span className="flex items-center gap-1.5 text-xs text-text-muted">
                  <Loader2 size={12} className="animate-spin text-primary" />
                  Yükleniyor...
                </span>
              )}
            </div>

            {historyError ? (
              <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-xs text-red-300 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <AlertCircle size={16} className="text-red-400 shrink-0" />
                  <span>{historyError}</span>
                </div>
                <button
                  onClick={handleRetryHistory}
                  className="px-2.5 py-1 rounded bg-red-600 hover:bg-red-500 text-white text-[11px] font-medium transition-colors flex items-center gap-1"
                >
                  <RotateCcw size={11} /> Tekrar Dene
                </button>
              </div>
            ) : historyLoading && !history ? (
              <div className="p-8 text-center text-xs text-text-muted space-y-2">
                <Loader2 size={24} className="animate-spin mx-auto text-primary" />
                <p>Geçmiş sipariş kayıtları getiriliyor...</p>
              </div>
            ) : !history || history.items.length === 0 ? (
              <div className="p-8 rounded-xl bg-surface/30 border border-border text-center space-y-2">
                <Package size={28} className="mx-auto text-text-muted opacity-50" />
                <h4 className="text-xs font-semibold text-text-primary">Sipariş Kaydı Bulunamadı</h4>
                <p className="text-xs text-text-muted max-w-sm mx-auto">
                  Bu tedarikçiye ait tamamlanmış veya kayıtlı geçmiş sipariş bulunmamaktadır.
                </p>
              </div>
            ) : (
              <div className="bg-surface/50 border border-border rounded-xl overflow-hidden shadow-sm flex flex-col">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-border bg-surface/80 text-text-muted uppercase text-[10px] tracking-wider">
                        <th className="p-3 font-semibold">Sipariş Ref / Kaynak</th>
                        <th className="p-3 font-semibold">Tarih</th>
                        <th className="p-3 font-semibold">Hedef / Gerçekleşen</th>
                        <th className="p-3 font-semibold">Gecikme</th>
                        <th className="p-3 font-semibold">Tutar ve Tür</th>
                        <th className="p-3 font-semibold">Durum</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {history.items.map((item) => {
                        const isCollision = item.has_collision;
                        return (
                          <tr 
                            key={item.id} 
                            className={`transition-colors hover:bg-surface/60 ${
                              isCollision ? "bg-amber-500/10 border-l-2 border-l-amber-500" : ""
                            }`}
                          >
                            {/* Ref & Source */}
                            <td className="p-3 align-top">
                              <div className="font-semibold text-text-primary font-mono text-[11px]">
                                {item.order_reference}
                              </div>
                              <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                                {item.source_type === "purchase_order" ? (
                                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                    Platform PO
                                  </span>
                                ) : (
                                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30">
                                    Harici ERP
                                  </span>
                                )}
                                {isCollision && (
                                  <span 
                                    className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold"
                                    title={item.collision_note || "Bu harici geçmiş kaydı, sistemdeki bir PO referansıyla eşleşmektedir ve çift sayılma riski taşır."}
                                  >
                                    ⚠️ Çakışma Riski
                                  </span>
                                )}
                              </div>
                              {isCollision && (
                                <div className="text-[10px] text-amber-300/80 mt-1 max-w-xs leading-tight">
                                  {item.collision_note || "Mükerrer PO eşleşmesi riski"}
                                </div>
                              )}
                            </td>

                            {/* Order Date */}
                            <td className="p-3 align-top text-text-secondary whitespace-nowrap">
                              {formatDate(item.order_date)}
                            </td>

                            {/* Delivery Dates */}
                            <td className="p-3 align-top text-text-secondary whitespace-nowrap">
                              <div className="text-[11px]">
                                <span className="text-text-muted">Hedef: </span>
                                {formatDate(item.expected_delivery_date)}
                              </div>
                              <div className="text-[11px] mt-0.5">
                                <span className="text-text-muted">Gerçek: </span>
                                {formatDate(item.actual_delivery_date)}
                              </div>
                            </td>

                            {/* Delay */}
                            <td className="p-3 align-top whitespace-nowrap">
                              {renderDelayBadge(item.delay_days)}
                            </td>

                            {/* Amount & Provenance */}
                            <td className="p-3 align-top whitespace-nowrap">
                              <div className="font-semibold text-text-primary">
                                {formatCurrency(item.amount, item.currency)}
                              </div>
                              <div className="text-[10px] text-text-muted mt-0.5">
                                {item.amount_type === "final_po_amount"
                                  ? "Kesin PO"
                                  : item.amount_type === "quoted_amount"
                                  ? "Teklif Tutarı"
                                  : "Harici Tutar"}
                              </div>
                            </td>

                            {/* Status */}
                            <td className="p-3 align-top whitespace-nowrap">
                              <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                                item.status === "completed"
                                  ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                                  : item.status === "delivered"
                                  ? "bg-blue-500/15 text-blue-400 border border-blue-500/30"
                                  : item.status === "cancelled"
                                  ? "bg-red-500/15 text-red-400 border border-red-500/30"
                                  : "bg-surface border border-border text-text-muted"
                              }`}>
                                {item.status}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Safe Pagination Controls */}
                <div className="p-3 border-t border-border bg-surface/70 flex items-center justify-between text-xs text-text-muted">
                  <span>
                    {totalCount === 0 
                      ? "Sipariş kaydı yok"
                      : `Sayfa ${currentPage} / ${totalPages} (${totalCount} Toplam Sipariş)`}
                  </span>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handlePageChange(historyPage - 1)}
                      disabled={historyPage <= 1 || historyLoading || totalPages <= 1}
                      className="px-2.5 py-1 rounded bg-surface border border-border hover:bg-bg disabled:opacity-40 disabled:cursor-not-allowed text-text-primary transition-colors flex items-center gap-1"
                    >
                      <ChevronLeft size={13} /> Önceki
                    </button>
                    <button
                      onClick={() => handlePageChange(historyPage + 1)}
                      disabled={historyPage >= totalPages || historyLoading || totalPages <= 1}
                      className="px-2.5 py-1 rounded bg-surface border border-border hover:bg-bg disabled:opacity-40 disabled:cursor-not-allowed text-text-primary transition-colors flex items-center gap-1"
                    >
                      Sonraki <ChevronRight size={13} />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

        </div>

        {/* ── Drawer Footer ────────────────────────────────────────────── */}
        <div className="p-4 border-t border-border bg-surface/70 flex items-center justify-between shrink-0">
          <span className="text-[11px] text-text-muted">
            Tedarikçi güvenilirlik verileri yasal denetim ve şeffaflık amacıyla sunulmaktadır.
          </span>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-surface border border-border hover:bg-bg text-text-primary text-xs font-semibold transition-colors"
          >
            Kapat
          </button>
        </div>

      </div>
    </div>
  );
};
