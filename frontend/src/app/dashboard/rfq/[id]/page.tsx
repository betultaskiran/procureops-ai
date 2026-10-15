"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { 
  ArrowLeft, 
  CheckCircle, 
  AlertTriangle, 
  FileText, 
  ShieldCheck, 
  Calculator,
  Download,
  Mail,
  Check,
  X,
  Loader2,
  ShieldAlert,
  UploadCloud,
  Plus,
  Trash2,
  Archive,
  ArchiveRestore,
  Ban,
  Sparkles,
  TrendingUp,
  RefreshCw,
  Clock
} from "lucide-react";
import { rfqsApi } from "@/lib/api/rfqs";
import { 
  RFQ, 
  Quote, 
  AnalysisResponse, 
  TCOResultResponse, 
  ComplianceCheckResponse, 
  EvidenceItemResponse, 
  PurchaseOrderResponse,
  ReviewResponse 
} from "@/lib/api/types";
import { ComparisonMatrix } from "@/components/analysis/ComparisonMatrix";
import { EvidencePanel } from "@/components/analysis/EvidencePanel";
import { StaleNoticeBanner } from "@/components/analysis/StaleNoticeBanner";
import { ReviewModal } from "@/components/analysis/ReviewModal";
import { SupplierPerformanceDrawer } from "@/components/analysis/SupplierPerformanceDrawer";

export default function RFQDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const [isDeleteRfqOpen, setIsDeleteRfqOpen] = useState(false);
  const [quoteToDelete, setQuoteToDelete] = useState<Quote | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Supplier Performance Drawer state
  const [drawerSupplier, setDrawerSupplier] = useState<{ id: string; name: string } | null>(null);
  
  // Cancel RFQ states
  const [isCancelRfqOpen, setIsCancelRfqOpen] = useState(false);
  const [rfqCancelReason, setRfqCancelReason] = useState("");
  const [rfqCancelPos, setRfqCancelPos] = useState(true);
  const [isCancellingRfq, setIsCancellingRfq] = useState(false);
  const [cancelRfqError, setCancelRfqError] = useState<string | null>(null);

  // Cancel PO states
  const [poToCancel, setPoToCancel] = useState<PurchaseOrderResponse | null>(null);
  const [poCancelReason, setPoCancelReason] = useState("");
  const [isCancellingPo, setIsCancellingPo] = useState(false);
  const [cancelPoError, setCancelPoError] = useState<string | null>(null);

  // Archive state
  const [isArchiving, setIsArchiving] = useState(false);

  const resolvedParams = React.use(params);
  const rfqId = resolvedParams.id;
  
  const [rfq, setRfq] = useState<RFQ | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [selectedQuoteId, setSelectedQuoteId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrderResponse[]>([]);
  
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Multi-Analysis & Review states
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [isReviewOpen, setIsReviewOpen] = useState(false);
  const [reviewQuoteId, setReviewQuoteId] = useState<string | null>(null);

  // Upload Quote Modal states
  const [isUploadQuoteOpen, setIsUploadQuoteOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadSupplierId, setUploadSupplierId] = useState("");
  const [suppliers, setSuppliers] = useState<{ id: string; name: string }[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadWarning, setUploadWarning] = useState<string | null>(null);

  // Inline supplier creation in modal
  const [isCreatingSupplier, setIsCreatingSupplier] = useState(false);
  const [newSupplierName, setNewSupplierName] = useState("");
  const [newSupplierEmail, setNewSupplierEmail] = useState("");
  const [newSupplierPhone, setNewSupplierPhone] = useState("");
  const [newSupplierCity, setNewSupplierCity] = useState("");
  const [isSavingSupplier, setIsSavingSupplier] = useState(false);
  const [supplierCreateError, setSupplierCreateError] = useState<string | null>(null);

  useEffect(() => {
    rfqsApi.getSuppliers().then(setSuppliers).catch(console.error);
  }, []);

  const handleBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push("/dashboard/quotes");
    }
  };

  const handleCancelRfq = async () => {
    if (!rfqCancelReason.trim() || rfqCancelReason.trim().length < 3) {
      setCancelRfqError("Lütfen en az 3 karakterlik bir iptal gerekçesi girin.");
      return;
    }
    try {
      setIsCancellingRfq(true);
      setCancelRfqError(null);
      const updated = await rfqsApi.cancelRfq(rfqId, rfqCancelReason.trim(), rfqCancelPos);
      setRfq(updated);
      setIsCancelRfqOpen(false);
      setRfqCancelReason("");
      const updatedPos = await rfqsApi.getPurchaseOrders(rfqId);
      setPurchaseOrders(updatedPos);
    } catch (err: any) {
      setCancelRfqError(err.message || "RFQ iptal edilirken bir hata oluştu.");
    } finally {
      setIsCancellingRfq(false);
    }
  };

  const handleArchiveRfq = async () => {
    try {
      setIsArchiving(true);
      const updated = await rfqsApi.archiveRfq(rfqId);
      setRfq(updated);
    } catch (err: any) {
      alert(err.message || "Arşivleme başarısız oldu.");
    } finally {
      setIsArchiving(false);
    }
  };

  const handleUnarchiveRfq = async () => {
    try {
      setIsArchiving(true);
      const updated = await rfqsApi.unarchiveRfq(rfqId);
      setRfq(updated);
    } catch (err: any) {
      alert(err.message || "Arşivden çıkarma başarısız oldu.");
    } finally {
      setIsArchiving(false);
    }
  };

  const handleCancelPo = async () => {
    if (!poToCancel) return;
    if (!poCancelReason.trim() || poCancelReason.trim().length < 3) {
      setCancelPoError("Lütfen en az 3 karakterlik bir iptal gerekçesi girin.");
      return;
    }
    try {
      setIsCancellingPo(true);
      setCancelPoError(null);
      const updatedPo = await rfqsApi.cancelPurchaseOrder(rfqId, poToCancel.id, poCancelReason.trim());
      setPurchaseOrders(prev => prev.map(p => p.id === updatedPo.id ? updatedPo : p));
      setPoToCancel(null);
      setPoCancelReason("");
      const updatedRfq = await rfqsApi.getRfq(rfqId);
      setRfq(updatedRfq);
    } catch (err: any) {
      setCancelPoError(err.message || "Sipariş iptal edilirken bir hata oluştu.");
    } finally {
      setIsCancellingPo(false);
    }
  };

  const handleDeleteRfq = async () => {
    try {
      setIsDeleting(true);
      setDeleteError(null);
      await rfqsApi.deleteRfq(rfqId);
      router.push("/dashboard/quotes");
    } catch (err: any) {
      setDeleteError(err.message || "RFQ silinirken bir hata oluştu.");
      setIsDeleting(false);
    }
  };

  const handleDeleteQuote = async () => {
    if (!quoteToDelete) return;
    try {
      setIsDeleting(true);
      setDeleteError(null);
      await rfqsApi.deleteQuote(quoteToDelete.id, rfqId);
      setQuotes(prev => prev.filter(q => q.id !== quoteToDelete.id));
      if (selectedQuoteId === quoteToDelete.id) {
        setSelectedQuoteId(null);
      }
      setQuoteToDelete(null);
      const updatedRfq = await rfqsApi.getRfq(rfqId);
      setRfq(updatedRfq);
      // Refresh analysis to reflect updated staleness
      rfqsApi.getAnalysis(rfqId).then(setAnalysis).catch(() => {});
    } catch (err: any) {
      setDeleteError(err.message || "Teklif silinirken bir hata oluştu.");
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCreateSupplier = async () => {
    if (!newSupplierName.trim()) {
      setSupplierCreateError("Lütfen tedarikçi adını girin.");
      return;
    }
    try {
      setIsSavingSupplier(true);
      setSupplierCreateError(null);
      const created = await rfqsApi.createSupplier({
        name: newSupplierName.trim(),
        email: newSupplierEmail.trim() || undefined,
        phone: newSupplierPhone.trim() || undefined,
        city: newSupplierCity.trim() || undefined,
      });
      setSuppliers(prev => [...prev, created]);
      setUploadSupplierId(created.id);
      setIsCreatingSupplier(false);
      setNewSupplierName("");
      setNewSupplierEmail("");
      setNewSupplierPhone("");
      setNewSupplierCity("");
    } catch (err: any) {
      setSupplierCreateError(err.message || "Tedarikçi eklenirken hata oluştu.");
    } finally {
      setIsSavingSupplier(false);
    }
  };

  const handleUploadSupplierQuote = async () => {
    if (!uploadFile || !uploadSupplierId) {
      setUploadError("Lütfen bir dosya ve tedarikçi seçin.");
      return;
    }
    try {
      setIsUploading(true);
      setUploadError(null);
      setUploadWarning(null);
      const res = await rfqsApi.uploadQuoteDocument(rfqId, uploadSupplierId, uploadFile);
      if (res.supplier_mismatch && res.warning) {
        setUploadWarning(res.warning);
      }
      // Re-fetch quotes without page reload
      const updatedQuotes = await rfqsApi.getRfqQuotes(rfqId);
      setQuotes(updatedQuotes);
      if (res.quote?.id) {
        setSelectedQuoteId(res.quote.id);
      }
      setIsUploadQuoteOpen(false);
      setUploadFile(null);
      // Refresh analysis to reflect updated staleness
      rfqsApi.getAnalysis(rfqId).then(setAnalysis).catch(() => {});
    } catch (err: any) {
      setUploadError(err.message || "Dosya yüklenirken bir hata oluştu.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleRunAnalysis = async () => {
    if (quotes.length < 2 || isAnalyzing) return;
    try {
      setIsAnalyzing(true);
      setAnalysisError(null);
      const res = await rfqsApi.analyzeRfq(rfqId, rfq?.organization_id || undefined);
      setAnalysis(res);
      const [updatedRfq, updatedQuotes] = await Promise.all([
        rfqsApi.getRfq(rfqId),
        rfqsApi.getRfqQuotes(rfqId),
      ]);
      setRfq(updatedRfq);
      setQuotes(updatedQuotes);
    } catch (err: any) {
      setAnalysisError(err.message || "Analiz çalıştırılırken bir hata oluştu.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleReviewSuccess = (review: ReviewResponse) => {
    Promise.allSettled([
      rfqsApi.getRfq(rfqId),
      rfqsApi.getPurchaseOrders(rfqId),
      rfqsApi.getAnalysis(rfqId),
      rfqsApi.getRfqQuotes(rfqId),
    ]).then(([rfqRes, poRes, analysisRes, quotesRes]) => {
      if (rfqRes.status === "fulfilled") setRfq(rfqRes.value);
      if (poRes.status === "fulfilled") setPurchaseOrders(poRes.value);
      if (analysisRes.status === "fulfilled") setAnalysis(analysisRes.value);
      if (quotesRes.status === "fulfilled") setQuotes(quotesRes.value);
    });
  };


  useEffect(() => {
    async function loadData() {
      try {
        setIsLoading(true);
        const [rfqRes, quotesRes, analysisRes, poRes] = await Promise.allSettled([
          rfqsApi.getRfq(rfqId),
          rfqsApi.getRfqQuotes(rfqId),
          rfqsApi.getAnalysis(rfqId),
          rfqsApi.getPurchaseOrders(rfqId)
        ]);

        if (rfqRes.status === 'fulfilled') {
          setRfq(rfqRes.value);
        } else {
          throw new Error("Failed to load core RFQ data.");
        }

        if (quotesRes.status === 'fulfilled') {
          setQuotes(quotesRes.value);
        }

        if (analysisRes.status === 'fulfilled') {
          setAnalysis(analysisRes.value);
        }

        if (poRes.status === 'fulfilled') {
          setPurchaseOrders(poRes.value);
        }

      } catch (err: any) {
        setError(err.message || "Failed to load RFQ details.");
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [rfqId]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-text-muted gap-3">
        <Loader2 size={32} className="animate-spin text-primary" />
        <p className="text-sm">Loading RFQ details...</p>
      </div>
    );
  }

  if (error || !rfq) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-red-500 gap-3">
        <ShieldAlert size={48} />
        <h2 className="text-xl font-semibold">Error Loading RFQ</h2>
        <p className="text-sm font-medium">{error || "RFQ not found."}</p>
        <button onClick={handleBack} className="text-sm text-primary hover:underline mt-4">Quotes & RFQs Sayfasına Dön</button>
      </div>
    );
  }

  // Find selected quote, or recommended quote if available, otherwise the first quote
  const recommendedQuoteId = analysis?.recommendation?.recommended_quote_id;
  const displayQuote = selectedQuoteId 
    ? (quotes.find(q => q.id === selectedQuoteId) || quotes[0])
    : (quotes.find(q => q.id === recommendedQuoteId) || quotes[0]);
  
  // Find TCO Result for this quote
  const displayTCO = analysis?.tco_results?.find(t => t.quote_id === displayQuote?.id);

  // Status Badge Helper
  const getStatusBadge = (status: string) => {
    switch(status.toLowerCase()) {
      case 'approved': return { bg: 'bg-success/10', border: 'border-success/20', text: 'text-success', dot: 'bg-success' };
      case 'rejected': return { bg: 'bg-red-500/10', border: 'border-red-500/20', text: 'text-red-500', dot: 'bg-red-500' };
      case 'cancelled': return { bg: 'bg-zinc-700/30', border: 'border-zinc-700/50', text: 'text-zinc-400', dot: 'bg-zinc-400' };
      case 'pending_approval': return { bg: 'bg-amber-500/10', border: 'border-amber-500/20', text: 'text-amber-500', dot: 'bg-amber-500' };
      case 'analyzing': return { bg: 'bg-blue-500/10', border: 'border-blue-500/20', text: 'text-blue-500', dot: 'bg-blue-500' };
      default: return { bg: 'bg-slate-500/10', border: 'border-slate-500/20', text: 'text-slate-400', dot: 'bg-slate-400' };
    }
  };
  
  const statusBadge = getStatusBadge(rfq.status);
  const formattedStatus = rfq.status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

  // Policy Warnings count
  const warningsCount = analysis?.compliance_checks?.filter(c => c.result !== 'pass').length || 0;

  return (
    <div className="flex flex-col gap-6">
      
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button 
            onClick={handleBack}
            title="Quotes & RFQs Sayfasına Dön"
            className="w-8 h-8 rounded-full border border-border flex items-center justify-center text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-text-primary">{rfq.title || rfq.id.split('-')[0]}</h1>
              <span className={`inline-flex items-center gap-1.5 ${statusBadge.bg} ${statusBadge.text} px-2.5 py-1 rounded-full text-[11px] font-medium border ${statusBadge.border}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${statusBadge.dot}`}></span>
                {formattedStatus}
              </span>
              {rfq.is_archived && (
                <span className="inline-flex items-center gap-1.5 bg-zinc-800 text-zinc-300 px-2.5 py-1 rounded-full text-[11px] font-medium border border-zinc-700">
                  <Archive size={12} />
                  Arşivlendi
                </span>
              )}
            </div>
            <p className="text-sm text-text-muted mt-1">Uploaded on {new Date(rfq.created_at).toLocaleDateString()}</p>
          </div>
        </div>
        
        <div className="flex items-center gap-2.5 flex-wrap">
          {rfq.status !== 'cancelled' && (
            <button 
              onClick={() => setIsUploadQuoteOpen(true)}
              className="flex items-center gap-2 bg-surface-elevated border border-border hover:bg-bg text-primary px-3.5 py-2 rounded text-xs font-medium transition-colors shadow-sm"
            >
              <Plus size={15} />
              Add Supplier Quote
            </button>
          )}

          {/* Multi-Analysis Action Button */}
          {rfq.status !== 'cancelled' && (
            <button
              onClick={handleRunAnalysis}
              disabled={isAnalyzing || quotes.length < 2}
              title={
                quotes.length < 2
                  ? "Karşılaştırmalı çoklu analiz için en az 2 tedarikçi teklifi yüklenmelidir."
                  : analysis
                  ? "Tüm teklifleri yeniden değerlendir ve TCO/uyum sonuçlarını güncelle"
                  : "Tüm teklifleri yan yana kıyaslayan yapay zeka analizini başlat"
              }
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded text-xs font-semibold transition-colors shadow-sm ${
                quotes.length < 2
                  ? "bg-surface border border-border text-text-muted opacity-50 cursor-not-allowed"
                  : isAnalyzing
                  ? "bg-primary/20 text-primary border border-primary/40 cursor-wait"
                  : "bg-primary hover:bg-primary-hover text-white"
              }`}
            >
              {isAnalyzing ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Analiz Ediliyor...</span>
                </>
              ) : (
                <>
                  <Sparkles size={14} />
                  <span>
                    {analysis ? "Analizi Yenile" : "Çoklu Analizi Başlat"}
                    {quotes.length < 2 && ` (${quotes.length}/2)`}
                  </span>
                </>
              )}
            </button>
          )}

          {/* Review & Decision Action */}
          {analysis && rfq.status !== 'cancelled' && purchaseOrders.filter(p => p.status !== 'cancelled').length === 0 && (
            <button 
              onClick={() => {
                setReviewQuoteId(selectedQuoteId || analysis.recommendation?.recommended_quote_id || quotes[0]?.id || null);
                setIsReviewOpen(true);
              }}
              className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-3.5 py-2 rounded text-xs font-semibold transition-colors shadow-sm"
            >
              <Check size={14} />
              <span>Karar Ver & Onayla</span>
            </button>
          )}

          {/* Archive / Unarchive */}
          {rfq.is_archived ? (
            <button
              onClick={handleUnarchiveRfq}
              disabled={isArchiving}
              title="Bu RFQ'yu arşivden çıkarıp aktif listeye al"
              className="flex items-center gap-1.5 px-3 py-2 rounded bg-surface-elevated border border-border hover:bg-bg text-xs font-medium text-text-secondary transition-colors"
            >
              <ArchiveRestore size={14} />
              Arşivden Çıkar
            </button>
          ) : (
            <button
              onClick={handleArchiveRfq}
              disabled={isArchiving}
              title="Bu RFQ'yu arşivle (aktif listeden kaldır)"
              className="flex items-center gap-1.5 px-3 py-2 rounded bg-surface-elevated border border-border hover:bg-bg text-xs font-medium text-text-muted hover:text-text-primary transition-colors"
            >
              <Archive size={14} />
              Arşivle
            </button>
          )}

          {/* Cancel RFQ */}
          {rfq.status !== 'cancelled' && (
            <button
              onClick={() => {
                setIsCancelRfqOpen(true);
                setCancelRfqError(null);
                setRfqCancelReason("");
              }}
              title="Bu RFQ iş akışını gerekçe belirterek iptal et"
              className="flex items-center gap-1.5 px-3 py-2 rounded border border-amber-500/30 text-amber-500 hover:bg-amber-500/10 text-xs font-medium transition-colors"
            >
              <Ban size={14} />
              İptal Et
            </button>
          )}
          
          {displayQuote?.quote_document_id && (
            <button className="flex items-center gap-2 bg-surface-elevated border border-border hover:bg-bg text-text-primary px-3.5 py-2 rounded text-xs font-medium transition-colors shadow-sm">
              <Download size={14} />
              Original Document
            </button>
          )}

          {/* Delete RFQ Action */}
          <button
            onClick={() => {
              if (rfq.can_delete) {
                setIsDeleteRfqOpen(true);
                setDeleteError(null);
              }
            }}
            disabled={!rfq.can_delete}
            title={rfq.can_delete ? "Bu RFQ talebini sil" : (rfq.delete_block_reason || "Onaylanmış veya PO oluşturulmuş RFQ silinemez")}
            className={`p-2 rounded border border-border transition-colors ${
              rfq.can_delete
                ? "text-text-muted hover:text-red-400 hover:bg-red-500/10"
                : "text-zinc-600 cursor-not-allowed opacity-40"
            }`}
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      {/* Upload Warning Banner */}
      {uploadWarning && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert size={18} />
            <span>{uploadWarning}</span>
          </div>
          <button onClick={() => setUploadWarning(null)} className="text-xs hover:underline font-medium">
            Kapat
          </button>
        </div>
      )}

      {/* Analysis Error Banner */}
      {analysisError && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert size={18} className="text-red-400 shrink-0" />
            <span>{analysisError}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRunAnalysis}
              className="px-2.5 py-1 rounded bg-red-600 hover:bg-red-500 text-white font-medium text-xs transition-colors"
            >
              Tekrar Dene
            </button>
            <button
              onClick={() => setAnalysisError(null)}
              className="text-xs hover:underline text-text-muted"
            >
              Kapat
            </button>
          </div>
        </div>
      )}

      {/* Stale Analysis Notice Banner */}
      {analysis && (
        <StaleNoticeBanner
          isStale={!!analysis.is_stale}
          isAnalyzing={isAnalyzing}
          onRerunAnalysis={handleRunAnalysis}
        />
      )}

      {/* RFQ Requirements Card */}
      <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-3 flex items-center gap-2">
          <FileText size={16} className="text-primary" />
          RFQ Requirements & Terms
        </h2>
        
        {rfq.description && (
          <p className="text-sm text-text-secondary mb-4">{rfq.description}</p>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-surface/50 rounded-lg border border-border mb-4 text-xs">
          <div>
            <span className="text-text-muted block">Target Budget</span>
            <span className="font-semibold text-text-primary mt-0.5 block">
              {rfq.budget ? new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(rfq.budget) : 'Not specified'}
            </span>
          </div>
          <div>
            <span className="text-text-muted block">Max Delivery</span>
            <span className="font-semibold text-text-primary mt-0.5 block">
              {rfq.max_delivery_days ? `${rfq.max_delivery_days} days` : 'Not specified'}
            </span>
          </div>
          <div>
            <span className="text-text-muted block">Min Warranty</span>
            <span className="font-semibold text-text-primary mt-0.5 block">
              {rfq.min_warranty_months ? `${rfq.min_warranty_months} months` : 'Not specified'}
            </span>
          </div>
          <div>
            <span className="text-text-muted block">Payment Terms</span>
            <span className="font-semibold text-text-primary mt-0.5 block">
              {rfq.payment_terms || 'Not specified'}
            </span>
          </div>
        </div>

        {rfq.items && rfq.items.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">Requested Items ({rfq.items.length})</h3>
            <div className="divide-y divide-border border border-border rounded-lg overflow-hidden bg-surface/30">
              {rfq.items.map((it) => (
                <div key={it.id} className="p-3 flex items-center justify-between text-xs">
                  <span className="font-medium text-text-primary">{it.line_number}. {it.description}</span>
                  <span className="text-text-muted">{it.quantity} {it.unit || 'Adet'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Multi-Analysis Comparison Matrix ──────────────────────────── */}
      {quotes.length >= 2 ? (
        <ComparisonMatrix
          quotes={quotes}
          rfq={rfq}
          analysis={analysis}
          selectedQuoteId={selectedQuoteId}
          onSelectQuote={setSelectedQuoteId}
          onOpenReviewModal={(qId) => {
            setReviewQuoteId(qId || null);
            setIsReviewOpen(true);
          }}
          onOpenSupplierDrawer={(suppId, suppName) => {
            setDrawerSupplier({ id: suppId, name: suppName });
          }}
        />
      ) : quotes.length === 1 ? (
        <div className="p-5 rounded-xl bg-surface-elevated border border-border shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center border border-amber-500/20 shrink-0">
              <AlertTriangle size={18} />
            </div>
            <div>
              <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider">
                Çoklu Karşılaştırma Beklemede (1 / 2 Teklif)
              </h3>
              <p className="text-xs text-text-muted mt-0.5">
                Tedarikçileri yan yana kıyaslamak ve yapay zeka analizini çalıştırmak için en az bir teklif daha eklenmelidir.
              </p>
            </div>
          </div>
          {rfq.status !== "cancelled" && (
            <button
              onClick={() => setIsUploadQuoteOpen(true)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary hover:bg-primary-hover text-white transition-colors shrink-0"
            >
              + İkinci Teklifi Yükle
            </button>
          )}
        </div>
      ) : (
        <div className="p-8 rounded-xl bg-surface-elevated border-2 border-dashed border-border text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-surface border border-border text-text-muted mx-auto flex items-center justify-center">
            <UploadCloud size={20} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">Henüz Teklif Eklenmedi</h3>
            <p className="text-xs text-text-muted mt-1 max-w-sm mx-auto">
              Bu satın alma talebi için tedarikçilerden gelen teklif belgelerini yükleyerek otomatik veri çıkarımı ve çoklu TCO analizi başlatabilirsiniz.
            </p>
          </div>
          {rfq.status !== "cancelled" && (
            <button
              onClick={() => setIsUploadQuoteOpen(true)}
              className="px-4 py-2 rounded-lg text-xs font-semibold bg-primary hover:bg-primary-hover text-white transition-colors inline-flex items-center gap-1.5"
            >
              <Plus size={14} />
              İlk Teklifi Ekle
            </button>
          )}
        </div>
      )}
      
      {/* Submitted Quotes Table */}
      {quotes.length > 0 && (
        <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider flex items-center gap-2">
              <FileText size={16} className="text-primary" />
              Submitted Quotes ({quotes.length})
            </h2>
            <span className="text-xs text-text-muted">Click &quot;View Details&quot; to inspect any quote below</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-text-muted uppercase bg-surface/50 border-b border-border">
                <tr>
                  <th className="px-4 py-3 font-medium">Supplier</th>
                  <th className="px-4 py-3 font-medium">Total Price</th>
                  <th className="px-4 py-3 font-medium">Delivery</th>
                  <th className="px-4 py-3 font-medium">Warranty</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {quotes.map(q => {
                  const isSelected = q.id === displayQuote?.id;
                  return (
                    <tr key={q.id} className={`hover:bg-surface/30 transition-colors ${isSelected ? 'bg-primary/10 border-l-4 border-l-primary' : ''}`}>
                      <td className="px-4 py-3 font-medium text-text-primary">
                        <div>{q.supplier_name || 'Unknown'}</div>
                        {q.extracted_supplier_name && q.extracted_supplier_name.toLowerCase() !== (q.supplier_name || '').toLowerCase() && (
                          <div className="text-[11px] text-amber-500 font-normal">
                            Doc: {q.extracted_supplier_name}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-text-secondary">{new Intl.NumberFormat('tr-TR', { style: 'currency', currency: q.currency || 'TRY' }).format(q.total_price)}</td>
                      <td className="px-4 py-3 text-text-secondary">{q.delivery_days ? `${q.delivery_days} days` : '-'}</td>
                      <td className="px-4 py-3 text-text-secondary">{q.warranty_months ? `${q.warranty_months} months` : '-'}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-success/10 text-success border border-success/20">
                          Extracted
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => setDrawerSupplier({ id: q.supplier_id, name: q.supplier_name || 'Tedarikçi' })}
                            title="Tedarikçi performans karnesi ve geçmiş siparişlerini incele"
                            className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-surface border border-transparent hover:border-border transition-colors"
                          >
                            <Clock size={13} />
                          </button>

                          <button 
                            onClick={() => setSelectedQuoteId(q.id)}
                            className={`text-xs font-semibold px-2.5 py-1 rounded transition-colors ${
                              isSelected
                                ? 'bg-primary text-white shadow-sm' 
                                : 'text-primary hover:bg-primary/10'
                            }`}
                          >
                            {isSelected ? 'Viewing' : 'View Details'}
                          </button>
                          
                          <button
                            onClick={() => {
                              if (q.can_delete) {
                                setQuoteToDelete(q);
                                setDeleteError(null);
                              }
                            }}
                            disabled={!q.can_delete}
                            title={q.can_delete ? "Bu teklifi sil" : (q.delete_block_reason || "Onaylanmış teklif silinemez")}
                            className={`p-1 rounded transition-colors ${
                              q.can_delete
                                ? "text-text-muted hover:text-red-400 hover:bg-red-500/10"
                                : "text-zinc-600 cursor-not-allowed opacity-40"
                            }`}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        
        {/* ── Left Column: Extraction, Evidence & Calculation ─────────────── */}
        <div className="lg:col-span-2 flex flex-col gap-6">

          {/* AI Recommendation, Reasoning, Risks, Citations & Hard Rules */}
          {analysis && (
            <EvidencePanel
              analysis={analysis}
              quotes={quotes}
              onOpenReviewModal={(qId) => {
                setReviewQuoteId(qId || null);
                setIsReviewOpen(true);
              }}
            />
          )}
          
          <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider flex items-center gap-2">
                <FileText size={16} className="text-primary" />
                {displayQuote ? `Quote Details: ${displayQuote.supplier_name || 'Unknown'}` : 'No Quote Available'}
              </h2>
              {displayQuote?.extracted_supplier_name && displayQuote.extracted_supplier_name.toLowerCase() !== (displayQuote.supplier_name || '').toLowerCase() && (
                <span className="text-xs text-amber-500 font-medium">
                  Belgeden Okunan: {displayQuote.extracted_supplier_name}
                </span>
              )}
            </div>
            
            {displayQuote ? (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-6">
                  <div>
                    <div className="text-xs text-text-muted mb-1">Supplier</div>
                    <div className="text-sm font-medium text-text-primary">{displayQuote.supplier_name || displayQuote.supplier_id}</div>
                  </div>
                  <div>
                    <div className="text-xs text-text-muted mb-1">Payment Terms</div>
                    <div className="text-sm font-medium text-text-primary">{displayQuote.payment_terms || 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-text-muted mb-1">Delivery Time</div>
                    <div className="text-sm font-medium text-text-primary">{displayQuote.delivery_days ? `${displayQuote.delivery_days} Days` : 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-text-muted mb-1">Warranty</div>
                    <div className="text-sm font-medium text-text-primary">{displayQuote.warranty_months ? `${displayQuote.warranty_months} Months` : 'N/A'}</div>
                  </div>
                </div>

                {/* Line Items Table */}
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-bg text-text-muted text-xs uppercase border-b border-border">
                      <tr>
                        <th className="px-4 py-3 font-medium">Item Description</th>
                        <th className="px-4 py-3 font-medium text-right">Qty</th>
                        <th className="px-4 py-3 font-medium text-right">Unit Price</th>
                        <th className="px-4 py-3 font-medium text-right">Total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {displayQuote.items?.map((item, idx) => (
                        <tr key={idx} className="hover:bg-bg/50">
                          <td className="px-4 py-3 text-text-primary">{item.description}</td>
                          <td className="px-4 py-3 text-right text-text-primary">{item.quantity} {item.unit || ''}</td>
                          <td className="px-4 py-3 text-right text-text-primary">₺ {item.unit_price.toLocaleString('en-US')}</td>
                          <td className="px-4 py-3 text-right font-medium text-text-primary">₺ {item.total_price.toLocaleString('en-US')}</td>
                        </tr>
                      ))}
                      {(!displayQuote.items || displayQuote.items.length === 0) && (
                        <tr>
                          <td colSpan={4} className="px-4 py-6 text-center text-text-muted">No line items extracted.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Calculation Summary */}
                <div className="mt-6 flex flex-col items-end gap-2 text-sm">
                  <div className="flex justify-between w-64 text-text-muted">
                    <span>Subtotal:</span>
                    <span>₺ {displayQuote.subtotal?.toLocaleString('en-US') || 0}</span>
                  </div>
                  {displayQuote.discount_amount != null && displayQuote.discount_amount > 0 && (
                    <div className="flex justify-between w-64 text-text-muted">
                      <span>Discount:</span>
                      <span className="text-success">- ₺ {displayQuote.discount_amount.toLocaleString('en-US')}</span>
                    </div>
                  )}
                  <div className="flex justify-between w-64 text-text-muted border-b border-border pb-2">
                    <span>
                      VAT ({displayQuote.vat_rate != null ? `${(displayQuote.vat_rate * 100).toFixed(0)}%` : "Belirtilmemiş"}):
                    </span>
                    <span>
                      {displayQuote.vat_amount != null
                        ? `₺ ${displayQuote.vat_amount.toLocaleString('en-US')}`
                        : "[Eksik Veri]"}
                    </span>
                  </div>
                  <div className="flex justify-between w-64 font-semibold text-text-primary text-base pt-1">
                    <span>Total Quote:</span>
                    <span>₺ {displayQuote.total_price?.toLocaleString('en-US') || 0}</span>
                  </div>
                  
                  {displayTCO && (
                    <>
                      <div className="flex justify-between w-64 font-semibold text-amber-500 text-base pt-2 border-t border-border mt-2">
                        <span>Computed TCO:</span>
                        <span>₺ {displayTCO.total_tco.toLocaleString('en-US')}</span>
                      </div>
                      <div className="flex items-center justify-end gap-1.5 text-xs text-primary mt-2 bg-primary/10 px-2 py-1 rounded w-64">
                        <Calculator size={12} />
                        <span>Deterministic math applied.</span>
                      </div>
                    </>
                  )}
                </div>
              </>
            ) : (
               <div className="py-8 text-center text-text-muted text-sm">
                 <p>No quotes have been added to this RFQ yet.</p>
               </div>
            )}
          </div>
        </div>

        {/* ── Right Column: Purchase Orders & Dispatch ─────────────────────── */}
        <div className="flex flex-col gap-6">

          {purchaseOrders.length > 0 ? (
            <div className="flex flex-col gap-4">
              {purchaseOrders.map(po => {
                const isPoCancelled = po.status === 'cancelled';
                return (
                  <div 
                    key={po.id} 
                    className={`rounded-xl p-5 shadow-sm border ${
                      isPoCancelled 
                        ? 'bg-red-950/20 border-red-500/30 text-text-primary' 
                        : 'bg-emerald-950/20 border-emerald-500/30 text-text-primary'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h2 className="text-sm font-semibold uppercase tracking-wider flex items-center gap-2">
                        {isPoCancelled ? (
                          <>
                            <Ban size={16} className="text-red-400" />
                            <span className="text-red-400">Sipariş İptal Edildi</span>
                          </>
                        ) : (
                          <>
                            <CheckCircle size={16} className="text-emerald-400" />
                            <span className="text-emerald-400">Satın Alma Siparişi Aktif</span>
                          </>
                        )}
                      </h2>
                      <span className={`px-2 py-0.5 rounded text-[11px] font-mono font-semibold border ${
                        isPoCancelled 
                          ? 'bg-red-500/20 text-red-300 border-red-500/40' 
                          : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      }`}>
                        {po.status.toUpperCase()}
                      </span>
                    </div>

                    <div className="bg-bg/60 rounded p-3 text-xs font-mono space-y-1 border border-border">
                      <div className="flex justify-between">
                        <span className="text-text-muted">PO No:</span>
                        <span className="font-semibold text-text-primary">{po.po_number}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">Oluşturulma:</span>
                        <span>{new Date(po.created_at).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">E-posta Bildirimi:</span>
                        <span>{po.email_sent ? "Gönderildi" : "Beklemede"}</span>
                      </div>
                      {isPoCancelled && (
                        <>
                          <div className="flex justify-between text-red-300 pt-1 border-t border-border">
                            <span className="text-text-muted">İptal Tarihi:</span>
                            <span>{po.cancelled_at ? new Date(po.cancelled_at).toLocaleString() : "-"}</span>
                          </div>
                          <div className="pt-1 text-red-300 text-xs">
                            <span className="text-text-muted block text-[10px] uppercase font-semibold">İptal Gerekçesi:</span>
                            <span className="italic block mt-0.5">{po.cancellation_reason || "Gerekçe belirtilmedi"}</span>
                          </div>
                        </>
                      )}
                    </div>

                    {!isPoCancelled && (
                      <div className="mt-3 flex justify-end">
                        <button
                          onClick={() => {
                            setPoToCancel(po);
                            setPoCancelReason("");
                            setCancelPoError(null);
                          }}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600/80 hover:bg-red-600 text-white text-xs font-medium transition-colors shadow-sm"
                        >
                          <Ban size={13} />
                          Siparişi İptal Et
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm text-white">
              <h2 className="text-sm font-semibold uppercase tracking-wider mb-2 flex items-center gap-2">
                <Mail size={16} className="text-primary" />
                Next Step: Dispatch
              </h2>
              <p className="text-xs text-slate-400 mb-4 leading-relaxed">
                If approved, the system will automatically generate a PDF Purchase Order and send an email to 
                <span className="text-slate-200 font-medium"> the selected supplier</span>.
              </p>
              <div className="bg-slate-800 rounded p-3 text-xs font-mono text-slate-300 border border-slate-700">
                Subject: Purchase Order PO-{rfq.id.split('-')[0]}<br/>
                Attached: PO-{rfq.id.split('-')[0]}.pdf
              </div>
            </div>
          )}

        </div>
      </div>

      {/* ── Multi-Analysis Review & Decision Modal ───────────────────────── */}
      {isReviewOpen && analysis && (
        <ReviewModal
          isOpen={isReviewOpen}
          onClose={() => setIsReviewOpen(false)}
          analysis={analysis}
          quotes={quotes}
          initialSelectedQuoteId={reviewQuoteId || selectedQuoteId}
          onSuccess={handleReviewSuccess}
        />
      )}

      {/* Upload Quote Modal */}
      {isUploadQuoteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-hover border border-border rounded-lg shadow-xl w-full max-w-md overflow-hidden flex flex-col">
            <div className="p-6 border-b border-border flex justify-between items-center bg-surface">
              <h3 className="text-lg font-semibold text-text-primary">Add Supplier Quote</h3>
              <button 
                onClick={() => setIsUploadQuoteOpen(false)}
                className="text-text-muted hover:text-text-primary transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 flex flex-col gap-4">
              {uploadError && (
                <div className="p-3 rounded bg-danger/10 border border-danger/20 text-danger text-sm">
                  {uploadError}
                </div>
              )}

              {/* Supplier Selection or Creation */}
              {isCreatingSupplier ? (
                <div className="flex flex-col gap-3 p-3 bg-surface rounded-lg border border-border">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-text-primary uppercase">New Supplier Details</span>
                    <button 
                      type="button"
                      onClick={() => { setIsCreatingSupplier(false); setSupplierCreateError(null); }}
                      className="text-xs text-text-muted hover:text-text-primary"
                    >
                      Back to list
                    </button>
                  </div>

                  {supplierCreateError && (
                    <div className="p-2 rounded bg-danger/10 border border-danger/20 text-danger text-xs font-medium">
                      {supplierCreateError}
                    </div>
                  )}

                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-text-secondary">Company Name *</label>
                    <input 
                      type="text"
                      placeholder="e.g. Acme Tech Solutions"
                      value={newSupplierName}
                      onChange={(e) => setNewSupplierName(e.target.value)}
                      className="px-2.5 py-1.5 text-xs bg-background border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-text-secondary">Email</label>
                      <input 
                        type="email"
                        placeholder="contact@acme.com"
                        value={newSupplierEmail}
                        onChange={(e) => setNewSupplierEmail(e.target.value)}
                        className="px-2.5 py-1.5 text-xs bg-background border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-text-secondary">Phone</label>
                      <input 
                        type="text"
                        placeholder="+90 555 000 0000"
                        value={newSupplierPhone}
                        onChange={(e) => setNewSupplierPhone(e.target.value)}
                        className="px-2.5 py-1.5 text-xs bg-background border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 mt-1">
                    <button 
                      type="button"
                      onClick={() => { setIsCreatingSupplier(false); setSupplierCreateError(null); }}
                      className="px-3 py-1.5 text-xs text-text-muted hover:text-text-primary"
                    >
                      Cancel
                    </button>
                    <button 
                      type="button"
                      onClick={handleCreateSupplier}
                      disabled={isSavingSupplier || !newSupplierName.trim()}
                      className="flex items-center gap-1.5 bg-primary hover:bg-primary-hover text-white px-3 py-1.5 rounded text-xs font-medium transition-colors disabled:opacity-50"
                    >
                      {isSavingSupplier && <Loader2 size={12} className="animate-spin" />}
                      Save Supplier
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-text-secondary">Supplier *</label>
                    <button 
                      type="button"
                      onClick={() => setIsCreatingSupplier(true)}
                      className="text-xs text-primary hover:text-primary-hover font-medium flex items-center gap-1"
                    >
                      <Plus size={14} /> Add New Supplier
                    </button>
                  </div>
                  <select 
                    value={uploadSupplierId}
                    onChange={(e) => setUploadSupplierId(e.target.value)}
                    className="w-full bg-background border border-border rounded px-3 py-2 text-text-primary focus:outline-none focus:border-primary transition-colors text-sm"
                  >
                    <option value="">Select a supplier...</option>
                    {suppliers.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-text-secondary">Quote Document (PDF) *</label>
                <div className="border-2 border-dashed border-border rounded-lg p-6 flex flex-col items-center justify-center text-center group hover:border-primary/50 transition-colors relative">
                  <input 
                    type="file" 
                    accept=".pdf,.xlsx,.xls"
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  />
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center mb-4 transition-transform
                    ${uploadFile ? 'bg-success/20 text-success' : 'bg-surface text-text-muted group-hover:scale-110 group-hover:text-primary'}`}>
                    <UploadCloud size={24} />
                  </div>
                  
                  {uploadFile ? (
                    <div className="flex flex-col items-center">
                      <p className="text-sm font-medium text-text-primary">{uploadFile.name}</p>
                      <p className="text-xs text-text-muted mt-1">Ready to upload</p>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm font-medium text-text-primary">Click to upload or drag and drop</p>
                      <p className="text-xs text-text-muted mt-1">PDF, Excel up to 10MB</p>
                    </>
                  )}
                </div>
              </div>

            </div>
            
            <div className="p-4 border-t border-border bg-surface flex justify-end gap-3">
              <button 
                onClick={() => setIsUploadQuoteOpen(false)}
                className="px-4 py-2 text-sm font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button 
                onClick={handleUploadSupplierQuote}
                disabled={isUploading || !uploadFile || !uploadSupplierId}
                className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-white px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm disabled:opacity-50"
              >
                {isUploading && <Loader2 size={14} className="animate-spin" />}
                {isUploading ? "Uploading..." : "Upload Quote"}
              </button>
            </div>
          </div>
        </div>
      )}


      {/* ── Modal: Delete RFQ Confirmation ── */}
      {isDeleteRfqOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <div className="flex items-center gap-3 text-red-400 mb-4">
                <div className="p-2.5 rounded-full bg-red-500/10 border border-red-500/20">
                  <AlertTriangle size={22} />
                </div>
                <h3 className="text-base font-semibold text-text-primary">RFQ Talebini Sil</h3>
              </div>
              <p className="text-sm text-text-muted">
                Bu RFQ talebini ve bağlı tüm teklif belgelerini kalıcı olarak silmek istediğinizden emin misiniz?
              </p>
              <div className="mt-4 p-3 rounded-lg bg-bg border border-border text-xs">
                <span className="font-mono text-text-muted">#{rfq.id.slice(0, 8)}</span>
                <p className="font-semibold text-text-primary mt-1">{rfq.title}</p>
              </div>
              {deleteError && (
                <div className="mt-3 p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                  {deleteError}
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button
                onClick={() => { setIsDeleteRfqOpen(false); setDeleteError(null); }}
                disabled={isDeleting}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                Vazgeç
              </button>
              <button
                onClick={handleDeleteRfq}
                disabled={isDeleting}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isDeleting && <Loader2 size={13} className="animate-spin" />}
                {isDeleting ? "Siliniyor..." : "Evet, RFQ'yu Sil"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Delete Quote Confirmation ── */}
      {quoteToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <div className="flex items-center gap-3 text-red-400 mb-4">
                <div className="p-2.5 rounded-full bg-red-500/10 border border-red-500/20">
                  <AlertTriangle size={22} />
                </div>
                <h3 className="text-base font-semibold text-text-primary">Teklifi Sil</h3>
              </div>
              <p className="text-sm text-text-muted">
                Bu tedarikçi teklifini silmek istediğinizden emin misiniz?
              </p>
              <div className="mt-4 p-3 rounded-lg bg-bg border border-border text-xs">
                <p className="font-semibold text-text-primary">{quoteToDelete.supplier_name || "Tedarikçi Teklifi"}</p>
                <p className="text-emerald-400 font-medium mt-1">
                  ₺{Number(quoteToDelete.total_price).toLocaleString("tr-TR")} {quoteToDelete.currency}
                </p>
              </div>
              {deleteError && (
                <div className="mt-3 p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                  {deleteError}
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button
                onClick={() => { setQuoteToDelete(null); setDeleteError(null); }}
                disabled={isDeleting}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                Vazgeç
              </button>
              <button
                onClick={handleDeleteQuote}
                disabled={isDeleting}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isDeleting && <Loader2 size={13} className="animate-spin" />}
                {isDeleting ? "Siliniyor..." : "Evet, Teklifi Sil"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Cancel RFQ Confirmation ── */}
      {isCancelRfqOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <div className="flex items-center gap-3 text-amber-500 mb-4">
                <div className="p-2.5 rounded-full bg-amber-500/10 border border-amber-500/20">
                  <Ban size={22} />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-text-primary">RFQ Talebini İptal Et</h3>
                  <p className="text-xs text-text-muted mt-0.5">İş akışı durumu 'cancelled' olarak değiştirilecektir.</p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    İptal Gerekçesi <span className="text-red-400">*</span>
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Örn: Proje bütçesi yönetim kurulu kararıyla iptal edildi veya talep gereksiz hale geldi..."
                    value={rfqCancelReason}
                    onChange={(e) => setRfqCancelReason(e.target.value)}
                    className="w-full text-xs p-3 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-amber-500 transition-colors"
                  />
                  <p className="text-[11px] text-text-muted mt-1">En az 3 karakter gereklidir. Denetim günlüğüne (Audit Log) kaydedilir.</p>
                </div>

                {purchaseOrders.some(p => p.status !== 'cancelled') && (
                  <label className="flex items-start gap-2.5 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={rfqCancelPos}
                      onChange={(e) => setRfqCancelPos(e.target.checked)}
                      className="mt-0.5 rounded border-amber-500 text-amber-500 focus:ring-0"
                    />
                    <span>Bağlı aktif Satın Alma Siparişlerini (PO) de otomatik olarak iptal et.</span>
                  </label>
                )}

                {cancelRfqError && (
                  <div className="p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                    {cancelRfqError}
                  </div>
                )}
              </div>
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button
                onClick={() => { setIsCancelRfqOpen(false); setCancelRfqError(null); }}
                disabled={isCancellingRfq}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                Vazgeç
              </button>
              <button
                onClick={handleCancelRfq}
                disabled={isCancellingRfq || !rfqCancelReason.trim() || rfqCancelReason.trim().length < 3}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isCancellingRfq && <Loader2 size={13} className="animate-spin" />}
                {isCancellingRfq ? "İptal Ediliyor..." : "Evet, RFQ'yu İptal Et"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Cancel PO Confirmation ── */}
      {poToCancel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <div className="flex items-center gap-3 text-red-400 mb-4">
                <div className="p-2.5 rounded-full bg-red-500/10 border border-red-500/20">
                  <Ban size={22} />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-text-primary">Siparişi İptal Et</h3>
                  <p className="text-xs text-text-muted font-mono mt-0.5">{poToCancel.po_number}</p>
                </div>
              </div>

              <div className="space-y-4">
                <p className="text-xs text-text-muted">
                  Bu işlem Satın Alma Siparişini 'cancelled' durumuna geçirecektir. Yasal ve denetim izi gereği PO ve teklif kayıtları fiziksel olarak silinmez.
                </p>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    İptal Gerekçesi <span className="text-red-400">*</span>
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Örn: Tedarikçi taahhüt edilen teslimat süresine uyamayacağını bildirdi..."
                    value={poCancelReason}
                    onChange={(e) => setPoCancelReason(e.target.value)}
                    className="w-full text-xs p-3 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-red-500 transition-colors"
                  />
                  <p className="text-[11px] text-text-muted mt-1">En az 3 karakter gereklidir.</p>
                </div>

                {cancelPoError && (
                  <div className="p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                    {cancelPoError}
                  </div>
                )}
              </div>
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button
                onClick={() => { setPoToCancel(null); setCancelPoError(null); }}
                disabled={isCancellingPo}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                Vazgeç
              </button>
              <button
                onClick={handleCancelPo}
                disabled={isCancellingPo || !poCancelReason.trim() || poCancelReason.trim().length < 3}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isCancellingPo && <Loader2 size={13} className="animate-spin" />}
                {isCancellingPo ? "İptal Ediliyor..." : "Evet, Siparişi İptal Et"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Supplier Performance Drawer ── */}
      <SupplierPerformanceDrawer
        isOpen={!!drawerSupplier}
        onClose={() => setDrawerSupplier(null)}
        supplierId={drawerSupplier?.id || ""}
        supplierName={drawerSupplier?.name || ""}
      />

    </div>
  );
}
