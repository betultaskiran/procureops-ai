"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { 
  FileText, 
  Plus, 
  Search, 
  Filter, 
  Trash2, 
  ChevronDown, 
  ChevronUp, 
  ExternalLink, 
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  ShieldAlert, 
  Loader2, 
  Building2, 
  Calendar, 
  DollarSign, 
  Layers, 
  X,
  FileCheck2,
  Sparkles,
  AlertCircle,
  Archive,
  ArchiveRestore,
  Ban
} from "lucide-react";
import { rfqsApi } from "@/lib/api/rfqs";
import { RFQ, Quote } from "@/lib/api/types";

export default function QuotesAndRfqsPage() {
  const router = useRouter();
  const [rfqs, setRfqs] = useState<RFQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search & Filtering
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Expandable Quotes Map
  const [expandedRfqIds, setExpandedRfqIds] = useState<Set<string>>(new Set());
  const [quotesCache, setQuotesCache] = useState<Record<string, Quote[]>>({});
  const [loadingQuotesFor, setLoadingQuotesFor] = useState<Set<string>>(new Set());

  // Delete Confirmation Modals
  const [rfqToDelete, setRfqToDelete] = useState<RFQ | null>(null);
  const [quoteToDelete, setQuoteToDelete] = useState<{ quote: Quote; rfqTitle: string } | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Feedback Notification (Toast)
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // RFQ Create Modal State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createTitle, setCreateTitle] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createBudget, setCreateBudget] = useState("");
  const [createMaxDeliveryDays, setCreateMaxDeliveryDays] = useState("");
  const [createMinWarrantyMonths, setCreateMinWarrantyMonths] = useState("");
  const [createPaymentTerms, setCreatePaymentTerms] = useState("net-30");
  const [createItems, setCreateItems] = useState<{ description: string; quantity: string; unit: string }[]>([
    { description: "", quantity: "1", unit: "Adet" }
  ]);
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const fetchRfqs = async (filter?: string) => {
    try {
      setIsLoading(true);
      const activeFilter = typeof filter === "string" ? filter : statusFilter;
      const isArchivedTab = activeFilter === "archived";
      const data = await rfqsApi.getRfqs({
        archivedOnly: isArchivedTab,
        includeArchived: false,
      });
      setRfqs(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || "Talepler yüklenirken hata oluştu.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRfqs();
  }, []);

  // Auto-hide toast feedback after 5 seconds
  useEffect(() => {
    if (feedback) {
      const timer = setTimeout(() => setFeedback(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [feedback]);

  // Toggle quote accordion row
  const toggleExpandRfq = async (rfqId: string) => {
    const next = new Set(expandedRfqIds);
    if (next.has(rfqId)) {
      next.delete(rfqId);
      setExpandedRfqIds(next);
      return;
    }

    next.add(rfqId);
    setExpandedRfqIds(next);

    // Fetch quotes if not yet cached
    if (!quotesCache[rfqId]) {
      try {
        setLoadingQuotesFor((prev) => new Set(prev).add(rfqId));
        const quotes = await rfqsApi.getRfqQuotes(rfqId);
        setQuotesCache((prev) => ({ ...prev, [rfqId]: quotes }));
      } catch (err: any) {
        console.error("Quotes fetch error:", err);
      } finally {
        setLoadingQuotesFor((prev) => {
          const updated = new Set(prev);
          updated.delete(rfqId);
          return updated;
        });
      }
    }
  };

  // Perform RFQ Deletion
  const confirmDeleteRfq = async () => {
    if (!rfqToDelete) return;
    try {
      setIsDeleting(true);
      setDeleteError(null);
      const res = await rfqsApi.deleteRfq(rfqToDelete.id);
      
      // Update local state immediately
      setRfqs((prev) => prev.filter((r) => r.id !== rfqToDelete.id));
      setQuotesCache((prev) => {
        const next = { ...prev };
        delete next[rfqToDelete.id];
        return next;
      });
      setFeedback({ type: "success", message: res.message || "RFQ talebi başarıyla silindi." });
      setRfqToDelete(null);
    } catch (err: any) {
      setDeleteError(err.message || "RFQ silinirken bir hata oluştu.");
    } finally {
      setIsDeleting(false);
    }
  };

  // Perform Quote Deletion
  const confirmDeleteQuote = async () => {
    if (!quoteToDelete) return;
    const { quote } = quoteToDelete;
    try {
      setIsDeleting(true);
      setDeleteError(null);
      const res = await rfqsApi.deleteQuote(quote.id, quote.rfq_id);
      
      // Update quotes cache for this RFQ
      setQuotesCache((prev) => {
        const current = prev[quote.rfq_id] || [];
        return {
          ...prev,
          [quote.rfq_id]: current.filter((q) => q.id !== quote.id)
        };
      });

      // Update RFQ quotes_count in state
      setRfqs((prev) => prev.map((r) => {
        if (r.id === quote.rfq_id) {
          const nextCount = Math.max(0, (r.quotes_count || 1) - 1);
          return {
            ...r,
            quotes_count: nextCount,
            status: nextCount === 0 && r.status === "collecting_quotes" ? "draft" : r.status
          };
        }
        return r;
      }));

      setFeedback({ type: "success", message: res.message || "Teklif başarıyla silindi." });
      setQuoteToDelete(null);
    } catch (err: any) {
      setDeleteError(err.message || "Teklif silinirken bir hata oluştu.");
    } finally {
      setIsDeleting(false);
    }
  };

  // Handle RFQ Creation
  const handleCreateRfq = async () => {
    if (!createTitle.trim()) {
      setCreateError("Lütfen bir RFQ başlığı girin.");
      return;
    }
    try {
      setIsCreating(true);
      setCreateError(null);

      const validItems = createItems
        .filter((it) => it.description.trim())
        .map((it) => ({
          description: it.description.trim(),
          quantity: parseFloat(it.quantity) || 1,
          unit: it.unit.trim() || null,
        }));

      const newRfq = await rfqsApi.createRfq({
        title: createTitle.trim(),
        description: createDescription.trim() || undefined,
        budget: createBudget ? parseFloat(createBudget) : undefined,
        max_delivery_days: createMaxDeliveryDays ? parseInt(createMaxDeliveryDays) : undefined,
        min_warranty_months: createMinWarrantyMonths ? parseInt(createMinWarrantyMonths) : undefined,
        payment_terms: createPaymentTerms.trim() || undefined,
        items: validItems.length > 0 ? validItems : undefined,
      });

      setIsCreateOpen(false);
      setFeedback({ type: "success", message: `RFQ '#RFQ-${newRfq.id.slice(0, 8).toUpperCase()}' oluşturuldu.` });
      // Redirect to newly created RFQ detail page
      router.push(`/dashboard/rfq/${newRfq.id}`);
    } catch (err: any) {
      setCreateError(err.message || "RFQ oluşturulurken hata meydana geldi.");
    } finally {
      setIsCreating(false);
    }
  };

  const handleTabChange = (tabId: string) => {
    setStatusFilter(tabId);
    fetchRfqs(tabId);
  };

  // Filtered RFQs
  const filteredRfqs = rfqs.filter((rfq) => {
    const matchesSearch = 
      rfq.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rfq.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rfq.items?.some((i) => i.description.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesStatus = 
      statusFilter === "all" || statusFilter === "archived" 
        ? true 
        : rfq.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const getStatusBadge = (status: string, hasPo?: boolean) => {
    switch (status) {
      case "draft":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-500/10 text-zinc-400 border border-zinc-500/20"><Clock size={12} /> Taslak</span>;
      case "collecting_quotes":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20"><Layers size={12} /> Teklif Toplanıyor</span>;
      case "analyzing":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20"><Sparkles size={12} /> Analiz Ediliyor</span>;
      case "pending_approval":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20"><AlertCircle size={12} /> Onay Bekliyor</span>;
      case "approved":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 size={12} /> {hasPo ? "PO Oluşturuldu" : "Onaylandı"}
          </span>
        );
      case "rejected":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20"><ShieldAlert size={12} /> Reddedildi</span>;
      case "cancelled":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-700/30 text-zinc-400 border border-zinc-700/50"><Ban size={12} /> İptal Edildi</span>;
      default:
        return <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-surface-elevated text-text-muted">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      
      {/* Toast Notification */}
      {feedback && (
        <div className={`p-4 rounded-lg flex items-center justify-between gap-3 text-sm border shadow-lg transition-all ${
          feedback.type === "success" 
            ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" 
            : "bg-red-500/15 text-red-300 border-red-500/30"
        }`}>
          <div className="flex items-center gap-2">
            {feedback.type === "success" ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
            <span>{feedback.message}</span>
          </div>
          <button onClick={() => setFeedback(null)} className="text-current hover:opacity-75">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-text-primary">Quotes & RFQs</h1>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
              {rfqs.length} Talep
            </span>
          </div>
          <p className="text-sm text-text-muted mt-1">
            Satın alma taleplerini (RFQ), bağlı tedarikçi tekliflerini ve yaşam döngülerini yönetin.
          </p>
        </div>

        <button 
          onClick={() => { setIsCreateOpen(true); setCreateError(null); }}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm self-start sm:self-auto"
        >
          <Plus size={16} />
          Yeni RFQ Talebi
        </button>
      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between bg-surface border border-border p-3.5 rounded-xl">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input 
            type="text" 
            placeholder="RFQ başlığı, talep no veya ürün açıklaması ara..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1 md:pb-0">
          <Filter size={15} className="text-text-muted shrink-0 ml-1" />
          <span className="text-xs text-text-muted shrink-0 mr-1">Durum:</span>
          {[
            { id: "all", label: "Tümü" },
            { id: "draft", label: "Taslak" },
            { id: "collecting_quotes", label: "Teklif Toplanıyor" },
            { id: "pending_approval", label: "Onay Bekliyor" },
            { id: "approved", label: "Onaylandı" },
            { id: "cancelled", label: "İptal Edilenler" },
            { id: "archived", label: "Arşivlenenler" }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                statusFilter === tab.id
                  ? "bg-primary text-white"
                  : "bg-surface-elevated text-text-muted hover:text-text-primary hover:bg-border"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* RFQ List Section */}
      {isLoading ? (
        <div className="bg-surface border border-border rounded-xl p-12 flex flex-col items-center justify-center gap-3 text-text-muted">
          <Loader2 size={32} className="animate-spin text-primary" />
          <p className="text-sm">Talepler ve teklifler yükleniyor...</p>
        </div>
      ) : error ? (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-8 flex items-center justify-center gap-3 text-red-400">
          <AlertTriangle size={24} />
          <span className="text-sm font-medium">{error}</span>
          <button onClick={() => fetchRfqs()} className="ml-4 underline text-xs">Yeniden Dene</button>
        </div>
      ) : filteredRfqs.length === 0 ? (
        <div className="bg-surface border border-border rounded-xl p-12 text-center flex flex-col items-center justify-center">
          <FileText size={40} className="text-text-muted mb-3 opacity-50" />
          <h3 className="text-base font-semibold text-text-primary">Uygun Talep Bulunamadı</h3>
          <p className="text-sm text-text-muted mt-1 max-w-sm">
            {searchQuery || statusFilter !== "all" 
              ? "Arama kriterlerinize uyan bir RFQ kaydı bulunmuyor." 
              : "Henüz oluşturulmuş bir satın alma talebi (RFQ) yok. Yeni bir talep oluşturarak başlayabilirsiniz."}
          </p>
          {!searchQuery && statusFilter === "all" && (
            <button
              onClick={() => setIsCreateOpen(true)}
              className="mt-4 flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} /> İlk RFQ Talebini Oluştur
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filteredRfqs.map((rfq) => {
            const isExpanded = expandedRfqIds.has(rfq.id);
            const quotes = quotesCache[rfq.id] || [];
            const isLoadingQuotes = loadingQuotesFor.has(rfq.id);
            const shortId = `RFQ-${rfq.id.slice(0, 8).toUpperCase()}`;
            const itemsSummary = rfq.items && rfq.items.length > 0
              ? `${rfq.items.length} Kalem: ${rfq.items.map(i => i.description).slice(0, 2).join(", ")}${rfq.items.length > 2 ? "..." : ""}`
              : "Kalem belirtilmemiş";

            return (
              <div 
                key={rfq.id}
                className="bg-surface border border-border rounded-xl overflow-hidden transition-all duration-200 shadow-sm hover:border-border-hover"
              >
                {/* RFQ Header Row */}
                <div className="p-4 sm:p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  
                  {/* Left Column: Info & Summary */}
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2.5 mb-1.5">
                      <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-surface-elevated text-text-muted border border-border">
                        #{shortId}
                      </span>
                      {getStatusBadge(rfq.status, rfq.has_po)}
                      {rfq.is_archived && (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700 flex items-center gap-1">
                          <Archive size={11} /> Arşivlendi
                        </span>
                      )}
                      {rfq.has_po && (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          Sipariş Kesildi
                        </span>
                      )}
                    </div>

                    <Link 
                      href={`/dashboard/rfq/${rfq.id}`}
                      className="text-base font-semibold text-text-primary hover:text-primary transition-colors block truncate"
                    >
                      {rfq.title}
                    </Link>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted mt-2">
                      <span className="flex items-center gap-1">
                        <Building2 size={13} className="opacity-70" />
                        {rfq.created_by_name || "ProcureOps Ekibi"}
                      </span>
                      <span className="flex items-center gap-1">
                        <Calendar size={13} className="opacity-70" />
                        {new Date(rfq.created_at).toLocaleDateString("tr-TR")}
                      </span>
                      <span className="text-text-secondary truncate max-w-xs sm:max-w-md">
                        {itemsSummary}
                      </span>
                    </div>
                  </div>

                  {/* Middle Column: Financials & Metrics */}
                  <div className="flex items-center gap-6 self-start lg:self-center shrink-0 border-t lg:border-t-0 pt-3 lg:pt-0 border-border">
                    <div className="flex flex-col">
                      <span className="text-[11px] font-medium text-text-muted">Hedef Bütçe</span>
                      <span className="text-sm font-semibold text-text-primary">
                        {rfq.budget ? `₺${rfq.budget.toLocaleString("tr-TR")}` : "Belirtilmedi"}
                      </span>
                    </div>

                    <div className="flex flex-col">
                      <span className="text-[11px] font-medium text-text-muted">Teklif Sayısı</span>
                      <button
                        onClick={() => toggleExpandRfq(rfq.id)}
                        className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
                      >
                        <FileCheck2 size={14} />
                        <span>{rfq.quotes_count ?? 0} Teklif</span>
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    </div>
                  </div>

                  {/* Right Column: Actions */}
                  <div className="flex items-center gap-2 self-end lg:self-center shrink-0 border-t lg:border-t-0 pt-3 lg:pt-0 border-border">
                    <Link
                      href={`/dashboard/rfq/${rfq.id}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-surface-elevated hover:bg-border text-text-primary border border-border transition-colors"
                    >
                      <ExternalLink size={13} />
                      Detay & Analiz
                    </Link>

                    {/* Quick Archive / Unarchive Action */}
                    {rfq.is_archived ? (
                      <button
                        onClick={async () => {
                          try {
                            await rfqsApi.unarchiveRfq(rfq.id);
                            setFeedback({ type: "success", message: `RFQ '${rfq.title}' arşivden çıkarıldı.` });
                            fetchRfqs();
                          } catch (e: any) {
                            setFeedback({ type: "error", message: e.message || "Arşivden çıkarma hatası" });
                          }
                        }}
                        title="Arşivden Çıkar"
                        className="p-2 rounded-lg text-xs text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors border border-border"
                      >
                        <ArchiveRestore size={15} />
                      </button>
                    ) : (
                      <button
                        onClick={async () => {
                          try {
                            await rfqsApi.archiveRfq(rfq.id);
                            setFeedback({ type: "success", message: `RFQ '${rfq.title}' arşivlendi.` });
                            fetchRfqs();
                          } catch (e: any) {
                            setFeedback({ type: "error", message: e.message || "Arşivleme hatası" });
                          }
                        }}
                        title="Arşivle (Aktif listeden kaldır)"
                        className="p-2 rounded-lg text-xs text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors border border-border"
                      >
                        <Archive size={15} />
                      </button>
                    )}

                    {/* Safe Delete RFQ Button */}
                    <button
                      onClick={() => {
                        if (rfq.can_delete) {
                          setRfqToDelete(rfq);
                          setDeleteError(null);
                        }
                      }}
                      disabled={!rfq.can_delete}
                      title={rfq.can_delete ? "Bu RFQ talebini sil" : (rfq.delete_block_reason || "Onaylanmış veya PO oluşturulmuş kayıt silinemez")}
                      className={`p-2 rounded-lg text-xs transition-colors ${
                        rfq.can_delete
                          ? "text-text-muted hover:text-red-400 hover:bg-red-500/10"
                          : "text-zinc-600 cursor-not-allowed opacity-40"
                      }`}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>

                </div>

                {/* Expandable Quotes Section */}
                {isExpanded && (
                  <div className="border-t border-border bg-bg/50 p-4 sm:p-5">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <FileCheck2 size={16} className="text-primary" />
                        <h4 className="text-xs font-semibold text-text-primary uppercase tracking-wider">
                          Bağlı Tedarikçi Teklifleri ({quotes.length})
                        </h4>
                      </div>
                      <Link
                        href={`/dashboard/rfq/${rfq.id}`}
                        className="text-xs text-primary hover:underline flex items-center gap-1"
                      >
                        + Yeni Teklif Belgesi Yükle
                      </Link>
                    </div>

                    {isLoadingQuotes ? (
                      <div className="py-6 flex items-center justify-center gap-2 text-text-muted text-xs">
                        <Loader2 size={16} className="animate-spin text-primary" />
                        <span>Teklifler getiriliyor...</span>
                      </div>
                    ) : quotes.length === 0 ? (
                      <div className="p-4 rounded-lg bg-surface border border-border text-center text-xs text-text-muted">
                        Bu RFQ talebi için henüz tedarikçi teklifi yüklenmemiş.
                        <Link href={`/dashboard/rfq/${rfq.id}`} className="text-primary underline ml-1">
                          Teklif yüklemek için RFQ detayına gidin.
                        </Link>
                      </div>
                    ) : (
                      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-surface-elevated border-b border-border text-text-muted uppercase tracking-wider text-[11px]">
                            <tr>
                              <th className="px-3.5 py-2.5 font-semibold">Tedarikçi</th>
                              <th className="px-3.5 py-2.5 font-semibold">Toplam Fiyat</th>
                              <th className="px-3.5 py-2.5 font-semibold">Teslimat</th>
                              <th className="px-3.5 py-2.5 font-semibold">Garanti</th>
                              <th className="px-3.5 py-2.5 font-semibold">Ödeme Vadesi</th>
                              <th className="px-3.5 py-2.5 font-semibold">Uyum</th>
                              <th className="px-3.5 py-2.5 font-semibold text-right">İşlem</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border text-text-primary">
                            {quotes.map((q) => (
                              <tr key={q.id} className="hover:bg-bg/40 transition-colors">
                                <td className="px-3.5 py-2.5 font-medium">
                                  {q.supplier_name || q.extracted_supplier_name || "Tedarikçi"}
                                </td>
                                <td className="px-3.5 py-2.5 font-semibold text-emerald-400">
                                  ₺{Number(q.total_price).toLocaleString("tr-TR")} {q.currency}
                                </td>
                                <td className="px-3.5 py-2.5 text-text-secondary">
                                  {q.delivery_days ? `${q.delivery_days} gün` : "-"}
                                </td>
                                <td className="px-3.5 py-2.5 text-text-secondary">
                                  {q.warranty_months ? `${q.warranty_months} ay` : "-"}
                                </td>
                                <td className="px-3.5 py-2.5 text-text-secondary">
                                  {q.payment_terms || "-"}
                                </td>
                                <td className="px-3.5 py-2.5">
                                  {q.is_compliant === true ? (
                                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                                      <CheckCircle2 size={11} /> Uyumlu
                                    </span>
                                  ) : q.is_compliant === false ? (
                                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-red-400 bg-red-500/10 px-2 py-0.5 rounded border border-red-500/20">
                                      <AlertTriangle size={11} /> Uyumsuz
                                    </span>
                                  ) : (
                                    <span className="text-[11px] text-text-muted bg-surface-elevated px-2 py-0.5 rounded">
                                      İncelenmedi
                                    </span>
                                  )}
                                </td>
                                <td className="px-3.5 py-2.5 text-right">
                                  <div className="flex items-center justify-end gap-1">
                                    <Link
                                      href={`/dashboard/rfq/${rfq.id}`}
                                      className="p-1.5 text-text-muted hover:text-text-primary rounded hover:bg-surface-elevated transition-colors"
                                      title="Teklifi RFQ sayfasında incele"
                                    >
                                      <ExternalLink size={14} />
                                    </Link>
                                    
                                    {/* Safe Delete Quote Button */}
                                    <button
                                      onClick={() => {
                                        if (q.can_delete) {
                                          setQuoteToDelete({ quote: q, rfqTitle: rfq.title });
                                          setDeleteError(null);
                                        }
                                      }}
                                      disabled={!q.can_delete}
                                      title={q.can_delete ? "Bu teklifi sil" : (q.delete_block_reason || "Onaylanmış veya PO oluşturulmuş teklif silinemez")}
                                      className={`p-1.5 rounded transition-colors ${
                                        q.can_delete
                                          ? "text-text-muted hover:text-red-400 hover:bg-red-500/10"
                                          : "text-zinc-600 cursor-not-allowed opacity-40"
                                      }`}
                                    >
                                      <Trash2 size={14} />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ── Modal: Delete RFQ Confirmation ─────────────────────────────────── */}
      {rfqToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-md w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-6">
              <div className="flex items-center gap-3 text-red-400 mb-4">
                <div className="p-2.5 rounded-full bg-red-500/10 border border-red-500/20">
                  <AlertTriangle size={22} />
                </div>
                <h3 className="text-base font-semibold text-text-primary">RFQ Talebini Sil</h3>
              </div>

              <p className="text-sm text-text-muted">
                Aşağıdaki satın alma talebini ve sisteme yüklenmiş tüm bağlı teklifleri silmek istediğinizden emin misiniz?
              </p>

              <div className="mt-4 p-3.5 rounded-lg bg-bg border border-border">
                <span className="font-mono text-xs text-text-muted">#RFQ-{rfqToDelete.id.slice(0, 8).toUpperCase()}</span>
                <p className="text-sm font-semibold text-text-primary mt-0.5">{rfqToDelete.title}</p>
                <div className="flex items-center gap-2 mt-2 text-xs text-text-secondary">
                  <span>{rfqToDelete.quotes_count ?? 0} Bağlı Teklif</span>
                  <span>•</span>
                  <span>Bütçe: {rfqToDelete.budget ? `₺${rfqToDelete.budget.toLocaleString("tr-TR")}` : "-"}</span>
                </div>
              </div>

              <div className="mt-3 text-xs text-amber-400/90 bg-amber-500/10 border border-amber-500/20 p-2.5 rounded-md">
                <strong>Dikkat:</strong> Bu işlem kalıcıdır. Yüklenmiş ham PDF/belge dosyaları diskten ve veritabanı kayıtlarından temizlenecektir.
              </div>

              {deleteError && (
                <div className="mt-3 p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                  {deleteError}
                </div>
              )}
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button
                onClick={() => { setRfqToDelete(null); setDeleteError(null); }}
                disabled={isDeleting}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                Vazgeç
              </button>
              <button
                onClick={confirmDeleteRfq}
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

      {/* ── Modal: Delete Quote Confirmation ───────────────────────────────── */}
      {quoteToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-md w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-6">
              <div className="flex items-center gap-3 text-red-400 mb-4">
                <div className="p-2.5 rounded-full bg-red-500/10 border border-red-500/20">
                  <AlertTriangle size={22} />
                </div>
                <h3 className="text-base font-semibold text-text-primary">Tedarikçi Teklifini Sil</h3>
              </div>

              <p className="text-sm text-text-muted">
                <strong>{quoteToDelete.rfqTitle}</strong> talebine ait bu tedarikçi teklifini silmek istediğinizden emin misiniz?
              </p>

              <div className="mt-4 p-3.5 rounded-lg bg-bg border border-border">
                <p className="text-sm font-semibold text-text-primary">
                  {quoteToDelete.quote.supplier_name || quoteToDelete.quote.extracted_supplier_name || "Tedarikçi Teklifi"}
                </p>
                <div className="flex items-center gap-2 mt-2 text-xs text-text-secondary">
                  <span className="font-semibold text-emerald-400">
                    ₺{Number(quoteToDelete.quote.total_price).toLocaleString("tr-TR")} {quoteToDelete.quote.currency}
                  </span>
                  <span>•</span>
                  <span>{quoteToDelete.quote.delivery_days ? `${quoteToDelete.quote.delivery_days} gün` : "Süre belirtilmedi"}</span>
                </div>
              </div>

              <div className="mt-3 text-xs text-text-muted bg-surface-elevated p-2.5 rounded-md border border-border">
                Teklif silindiğinde ilişkili ham belge diski ve analiz TCO kayıtları temizlenir.
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
                onClick={confirmDeleteQuote}
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

      {/* ── Modal: Create New RFQ ────────────────────────────────────────── */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-6 border-b border-border flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-text-primary">Yeni RFQ Talebi Oluştur</h3>
                <p className="text-xs text-text-muted mt-0.5">Satın alma talebinizi ve ticari şartları belirleyin</p>
              </div>
              <button 
                onClick={() => setIsCreateOpen(false)}
                className="text-text-muted hover:text-text-primary p-1 rounded-md"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4 flex-1">
              {createError && (
                <div className="p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                  {createError}
                </div>
              )}

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-text-primary">Talep Başlığı *</label>
                <input
                  type="text"
                  placeholder="örn: 50 Adet İş İstasyonu ve Sunucu Donanımı"
                  value={createTitle}
                  onChange={(e) => setCreateTitle(e.target.value)}
                  className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-text-primary">Açıklama</label>
                <textarea
                  placeholder="Satın alma talebine dair ek detaylar, gereksinimler..."
                  rows={2}
                  value={createDescription}
                  onChange={(e) => setCreateDescription(e.target.value)}
                  className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                />
              </div>

              {/* Items Section */}
              <div className="space-y-2 pt-2 border-t border-border">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-text-primary uppercase tracking-wider">İstenen Kalemler</label>
                  <button 
                    type="button"
                    onClick={() => setCreateItems(prev => [...prev, { description: "", quantity: "1", unit: "Adet" }])}
                    className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
                  >
                    <Plus size={13} /> Kalem Ekle
                  </button>
                </div>

                <div className="space-y-2">
                  {createItems.map((item, idx) => (
                    <div key={idx} className="flex gap-2 items-center">
                      <input 
                        type="text" 
                        placeholder="Kalem açıklaması (örn. Sunucu Node)"
                        value={item.description}
                        onChange={(e) => {
                          const next = [...createItems];
                          next[idx].description = e.target.value;
                          setCreateItems(next);
                        }}
                        className="flex-1 px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                      />
                      <input 
                        type="number" 
                        placeholder="Miktar"
                        value={item.quantity}
                        onChange={(e) => {
                          const next = [...createItems];
                          next[idx].quantity = e.target.value;
                          setCreateItems(next);
                        }}
                        className="w-20 px-2.5 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                      />
                      <input 
                        type="text" 
                        placeholder="Birim"
                        value={item.unit}
                        onChange={(e) => {
                          const next = [...createItems];
                          next[idx].unit = e.target.value;
                          setCreateItems(next);
                        }}
                        className="w-20 px-2.5 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                      />
                      {createItems.length > 1 && (
                        <button 
                          type="button"
                          onClick={() => setCreateItems(prev => prev.filter((_, i) => i !== idx))}
                          className="p-2 text-text-muted hover:text-red-400 rounded"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Conditions / Budget */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-border">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-text-secondary">Hedef Bütçe (TRY)</label>
                  <input 
                    type="number"
                    placeholder="örn: 750000"
                    value={createBudget}
                    onChange={(e) => setCreateBudget(e.target.value)}
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-text-secondary">Maksimum Teslimat (Gün)</label>
                  <input 
                    type="number"
                    placeholder="örn: 20"
                    value={createMaxDeliveryDays}
                    onChange={(e) => setCreateMaxDeliveryDays(e.target.value)}
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-text-secondary">Minimum Garanti (Ay)</label>
                  <input 
                    type="number"
                    placeholder="örn: 24"
                    value={createMinWarrantyMonths}
                    onChange={(e) => setCreateMinWarrantyMonths(e.target.value)}
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-text-secondary">Ödeme Vadesi</label>
                  <input 
                    type="text"
                    placeholder="örn: net-30, peşin"
                    value={createPaymentTerms}
                    onChange={(e) => setCreatePaymentTerms(e.target.value)}
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                  />
                </div>
              </div>
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button 
                onClick={() => setIsCreateOpen(false)}
                disabled={isCreating}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                Vazgeç
              </button>
              <button 
                onClick={handleCreateRfq}
                disabled={isCreating || !createTitle.trim()}
                className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-xs font-medium transition-colors shadow-sm disabled:opacity-50"
              >
                {isCreating && <Loader2 size={13} className="animate-spin" />}
                {isCreating ? "Oluşturuluyor..." : "RFQ Talebi Oluştur"}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
