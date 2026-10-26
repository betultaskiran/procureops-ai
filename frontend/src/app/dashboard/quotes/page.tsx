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
  ChevronLeft,
  ChevronRight,
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
import { useTranslation } from "@/lib/i18n";
import { formatCurrency as fmtCurrency, formatDate as fmtDate, formatNumber as fmtNumber } from "@/lib/i18n/formatters";
import { getLocalizedApiError } from "@/lib/i18n/apiErrorMap";

export default function QuotesAndRfqsPage() {
  const router = useRouter();
  const { t, locale } = useTranslation();
  const [rfqs, setRfqs] = useState<RFQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pagination State
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(0);

  // Search & Filtering
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
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

  const resetCreateModal = () => {
    setIsCreateOpen(false);
    setCreateTitle("");
    setCreateDescription("");
    setCreateBudget("");
    setCreateMaxDeliveryDays("");
    setCreateMinWarrantyMonths("");
    setCreatePaymentTerms("net-30");
    setCreateItems([{ description: "", quantity: "1", unit: "Adet" }]);
    setCreateError(null);
  };

  const openCreateModal = () => {
    setCreateTitle("");
    setCreateDescription("");
    setCreateBudget("");
    setCreateMaxDeliveryDays("");
    setCreateMinWarrantyMonths("");
    setCreatePaymentTerms("net-30");
    setCreateItems([{ description: "", quantity: "1", unit: "Adet" }]);
    setCreateError(null);
    setIsCreateOpen(true);
  };

  // Debounce search query by 300ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // When debounced search or status filter changes, reset to page 1
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, statusFilter]);

  const fetchRfqs = async (
    targetPage: number = page,
    targetPageSize: number = pageSize,
    targetStatus: string = statusFilter,
    targetSearch: string = debouncedSearch
  ) => {
    try {
      setIsLoading(true);
      const isArchivedTab = targetStatus === "archived";
      const data = await rfqsApi.getRfqs({
        page: targetPage,
        pageSize: targetPageSize,
        status: targetStatus === "archived" ? undefined : targetStatus,
        search: targetSearch || undefined,
        archivedOnly: isArchivedTab,
        includeArchived: false,
      });
      const items = Array.isArray(data?.items) 
        ? data.items 
        : Array.isArray(data) 
          ? (data as unknown as RFQ[]) 
          : [];
      setRfqs(items);
      setTotalCount(data?.total_count ?? items.length);
      setTotalPages(data?.total_pages ?? (Math.ceil(items.length / targetPageSize) || 1));
      setError(null);
    } catch (err: any) {
      setRfqs([]);
      setError(getLocalizedApiError(err, locale));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRfqs(page, pageSize, statusFilter, debouncedSearch);
  }, [page, pageSize, statusFilter, debouncedSearch]);

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
      setRfqs((prev) => (Array.isArray(prev) ? prev.filter((r) => r.id !== rfqToDelete.id) : []));
      setQuotesCache((prev) => {
        const next = { ...prev };
        delete next[rfqToDelete.id];
        return next;
      });
      setFeedback({ type: "success", message: t("quotes_page.toast_rfq_deleted") });
      setRfqToDelete(null);
      await fetchRfqs(page, pageSize, statusFilter, debouncedSearch);
    } catch (err: any) {
      setDeleteError(getLocalizedApiError(err, locale));
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
      setRfqs((prev) => (Array.isArray(prev) ? prev.map((r) => {
        if (r.id === quote.rfq_id) {
          const nextCount = Math.max(0, (r.quotes_count || 1) - 1);
          return {
            ...r,
            quotes_count: nextCount,
            status: nextCount === 0 && r.status === "collecting_quotes" ? "draft" : r.status
          };
        }
        return r;
      }) : []));

      setFeedback({ type: "success", message: t("quotes_page.toast_quote_deleted") });
      setQuoteToDelete(null);
    } catch (err: any) {
      setDeleteError(getLocalizedApiError(err, locale));
    } finally {
      setIsDeleting(false);
    }
  };

  // Handle RFQ Creation
  const handleCreateRfq = async () => {
    if (!createTitle.trim()) {
      setCreateError(t("quotes_page.err_title_required"));
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

      resetCreateModal();
      setFeedback({ type: "success", message: t("quotes_page.toast_rfq_created") });
      // Redirect to newly created RFQ detail page
      router.push(`/dashboard/rfq/${newRfq.id}`);
    } catch (err: any) {
      setCreateError(getLocalizedApiError(err, locale));
    } finally {
      setIsCreating(false);
    }
  };

  const handleTabChange = (tabId: string) => {
    setStatusFilter(tabId);
    setPage(1);
  };

  const getStatusBadge = (status: string, hasPo?: boolean) => {
    switch (status) {
      case "draft":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-500/10 text-zinc-400 border border-zinc-500/20"><Clock size={12} /> {t("quotes_page.status.draft")}</span>;
      case "collecting_quotes":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20"><Layers size={12} /> {t("quotes_page.status.collecting_quotes")}</span>;
      case "analyzing":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20"><Sparkles size={12} /> {t("quotes_page.status.analyzing")}</span>;
      case "pending_approval":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20"><AlertCircle size={12} /> {t("quotes_page.status.pending_approval")}</span>;
      case "approved":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 size={12} /> {hasPo ? t("quotes_page.status.po_created") : t("quotes_page.status.approved")}
          </span>
        );
      case "rejected":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20"><ShieldAlert size={12} /> {t("quotes_page.status.rejected")}</span>;
      case "cancelled":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-700/30 text-zinc-400 border border-zinc-700/50"><Ban size={12} /> {t("quotes_page.status.cancelled")}</span>;
      default:
        return <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-surface-elevated text-text-muted">{status}</span>;
    }
  };

  const rfqList = Array.isArray(rfqs) ? rfqs : [];

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
            <h1 className="text-2xl font-bold tracking-tight text-text-primary">{t("quotes_page.title")}</h1>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
              {t("quotes_page.total_rfqs", { count: totalCount })}
            </span>
          </div>
          <p className="text-sm text-text-muted mt-1">
            {t("quotes_page.subtitle")}
          </p>
        </div>

        <button 
          onClick={openCreateModal}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm self-start sm:self-auto"
        >
          <Plus size={16} />
          {t("quotes_page.create_rfq")}
        </button>
      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between bg-surface border border-border p-3.5 rounded-xl">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input 
            type="text" 
            placeholder={t("quotes_page.search_placeholder")} 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1 md:pb-0">
          <Filter size={15} className="text-text-muted shrink-0 ml-1" />
          <span className="text-xs text-text-muted shrink-0 mr-1">{t("quotes_page.filter_label")}</span>
          {[
            { id: "all", label: t("quotes_page.filter_all") },
            { id: "draft", label: t("quotes_page.status.draft") },
            { id: "collecting_quotes", label: t("quotes_page.filter_collecting") },
            { id: "pending_approval", label: t("quotes_page.status.pending_approval") },
            { id: "approved", label: t("quotes_page.status.approved") },
            { id: "cancelled", label: t("quotes_page.filter_cancelled") },
            { id: "archived", label: t("quotes_page.filter_archived") }
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
          <p className="text-sm">{t("quotes_page.loading")}</p>
        </div>
      ) : error ? (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-8 flex items-center justify-center gap-3 text-red-400">
          <AlertTriangle size={24} />
          <span className="text-sm font-medium">{error}</span>
          <button onClick={() => fetchRfqs()} className="ml-4 underline text-xs">{t("quotes_page.retry")}</button>
        </div>
      ) : rfqList.length === 0 ? (
        <div className="bg-surface border border-border rounded-xl p-12 text-center flex flex-col items-center justify-center">
          <FileText size={40} className="text-text-muted mb-3 opacity-50" />
          <h3 className="text-base font-semibold text-text-primary">{searchQuery || statusFilter !== "all" ? t("quotes_page.no_results_title") : t("quotes_page.empty_initial_title")}</h3>
          <p className="text-sm text-text-muted mt-1 max-w-sm">
            {debouncedSearch || statusFilter !== "all" 
              ? t("quotes_page.no_results_desc") 
              : t("quotes_page.empty_initial_desc")}
          </p>
          {!debouncedSearch && statusFilter === "all" && (
            <button
              onClick={openCreateModal}
              className="mt-4 flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} /> {t("quotes_page.empty_create_btn")}
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {rfqList.map((rfq) => {
            const isExpanded = expandedRfqIds.has(rfq.id);
            const quotes = quotesCache[rfq.id] || [];
            const isLoadingQuotes = loadingQuotesFor.has(rfq.id);
            const shortId = `RFQ-${rfq.id.slice(0, 8).toUpperCase()}`;
            const itemsSummary = rfq.items && rfq.items.length > 0
              ? `${t("quotes_page.items_count", { count: rfq.items.length })}: ${rfq.items.map(i => i.description).slice(0, 2).join(", ")}${rfq.items.length > 2 ? "..." : ""}`
              : t("quotes_page.no_items_specified");

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
                          <Archive size={11} /> {t("quotes_page.status.archived")}
                        </span>
                      )}
                      {rfq.has_po && (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          {t("quotes_page.status.po_created")}
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
                        {fmtDate(rfq.created_at, locale)}
                      </span>
                      <span className="text-text-secondary truncate max-w-xs sm:max-w-md">
                        {itemsSummary}
                      </span>
                    </div>
                  </div>

                  {/* Middle Column: Financials & Metrics */}
                  <div className="flex items-center gap-6 self-start lg:self-center shrink-0 border-t lg:border-t-0 pt-3 lg:pt-0 border-border">
                    <div className="flex flex-col">
                      <span className="text-[11px] font-medium text-text-muted">{t("quotes_page.table_total_price")}</span>
                      <span className="text-sm font-semibold text-text-primary">
                        {rfq.budget ? `₺${rfq.budget.toLocaleString(locale === "en" ? "en-US" : "tr-TR")}` : t("quotes_page.not_specified")}
                      </span>
                    </div>

                    <div className="flex flex-col">
                      <span className="text-[11px] font-medium text-text-muted">{t("quotes_page.col_quotes")}</span>
                      <button
                        onClick={() => toggleExpandRfq(rfq.id)}
                        className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
                      >
                        <FileCheck2 size={14} />
                        <span>{t("quotes_page.quotes_count", { count: rfq.quotes_count ?? 0 })}</span>
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
                      {t("quotes_page.view_details")}
                    </Link>

                    {/* Quick Archive / Unarchive Action */}
                    {rfq.is_archived ? (
                      <button
                        onClick={async () => {
                          try {
                            await rfqsApi.unarchiveRfq(rfq.id);
                            setFeedback({ type: "success", message: t("quotes_page.toast_rfq_unarchived", { title: rfq.title }) });
                            fetchRfqs();
                          } catch (e: any) {
                            setFeedback({ type: "error", message: getLocalizedApiError(e, locale) });
                          }
                        }}
                        title={t("quotes_page.unarchive_tooltip")}
                        className="p-2 rounded-lg text-xs text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors border border-border"
                      >
                        <ArchiveRestore size={15} />
                      </button>
                    ) : (
                      <button
                        onClick={async () => {
                          try {
                            await rfqsApi.archiveRfq(rfq.id);
                            setFeedback({ type: "success", message: t("quotes_page.toast_rfq_archived", { title: rfq.title }) });
                            fetchRfqs();
                          } catch (e: any) {
                            setFeedback({ type: "error", message: getLocalizedApiError(e, locale) });
                          }
                        }}
                        title={t("quotes_page.archive_tooltip")}
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
                      title={rfq.can_delete ? t("quotes_page.delete_rfq_title") : (rfq.delete_block_reason || t("quotes_page.delete_rfq_blocked"))}
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
                          {t("quotes_page.connected_quotes_title", { count: quotes.length })}
                        </h4>
                      </div>
                      <Link
                        href={`/dashboard/rfq/${rfq.id}`}
                        className="text-xs text-primary hover:underline flex items-center gap-1"
                      >
                        {t("quotes_page.upload_quote_btn")}
                      </Link>
                    </div>

                    {isLoadingQuotes ? (
                      <div className="py-6 flex items-center justify-center gap-2 text-text-muted text-xs">
                        <Loader2 size={16} className="animate-spin text-primary" />
                        <span>{t("quotes_page.loading_quotes")}</span>
                      </div>
                    ) : quotes.length === 0 ? (
                      <div className="p-4 rounded-lg bg-surface border border-border text-center text-xs text-text-muted">
                        {t("quotes_page.empty_connected_quotes")}
                        <Link href={`/dashboard/rfq/${rfq.id}`} className="text-primary underline ml-1">
                          {t("quotes_page.empty_connected_quotes_action")}
                        </Link>
                      </div>
                    ) : (
                      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-surface-elevated border-b border-border text-text-muted uppercase tracking-wider text-[11px]">
                            <tr>
                              <th className="px-3.5 py-2.5 font-semibold">{t("quotes_page.table_supplier")}</th>
                              <th className="px-3.5 py-2.5 font-semibold">{t("quotes_page.table_total_price")}</th>
                              <th className="px-3.5 py-2.5 font-semibold">{t("quotes_page.table_delivery")}</th>
                              <th className="px-3.5 py-2.5 font-semibold">{t("quotes_page.table_warranty")}</th>
                              <th className="px-3.5 py-2.5 font-semibold">{t("quotes_page.table_payment")}</th>
                              <th className="px-3.5 py-2.5 font-semibold">{t("quotes_page.table_compliance")}</th>
                              <th className="px-3.5 py-2.5 font-semibold text-right">{t("quotes_page.table_action")}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border text-text-primary">
                            {quotes.map((q) => (
                              <tr key={q.id} className="hover:bg-bg/40 transition-colors">
                                <td className="px-3.5 py-2.5 font-medium">
                                  {q.supplier_name || q.extracted_supplier_name || t("quotes_page.table_supplier")}
                                </td>
                                <td className="px-3.5 py-2.5 font-semibold text-emerald-400">
                                  {fmtCurrency(Number(q.total_price), q.currency, locale)}
                                </td>
                                <td className="px-3.5 py-2.5 text-text-secondary">
                                  {q.delivery_days ? t("rfq_detail.days_unit", { count: q.delivery_days }) : "-"}
                                </td>
                                <td className="px-3.5 py-2.5 text-text-secondary">
                                  {q.warranty_months ? `${q.warranty_months} ${locale === "tr" ? "ay" : "mo"}` : "-"}
                                </td>
                                <td className="px-3.5 py-2.5 text-text-secondary">
                                  {q.payment_terms || "-"}
                                </td>
                                <td className="px-3.5 py-2.5">
                                  {q.is_compliant === true ? (
                                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                                      <CheckCircle2 size={11} /> {t("quotes_page.compliant")}
                                    </span>
                                  ) : q.is_compliant === false ? (
                                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-red-400 bg-red-500/10 px-2 py-0.5 rounded border border-red-500/20">
                                      <AlertTriangle size={11} /> {t("quotes_page.non_compliant")}
                                    </span>
                                  ) : (
                                    <span className="text-[11px] text-text-muted bg-surface-elevated px-2 py-0.5 rounded">
                                      {t("quotes_page.not_reviewed")}
                                    </span>
                                  )}
                                </td>
                                <td className="px-3.5 py-2.5 text-right">
                                  <div className="flex items-center justify-end gap-1">
                                    <Link
                                      href={`/dashboard/rfq/${rfq.id}`}
                                      className="p-1.5 text-text-muted hover:text-text-primary rounded hover:bg-surface-elevated transition-colors"
                                      title={t("quotes_page.view_quote_tooltip")}
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
                                      title={q.can_delete ? t("quotes_page.delete_quote_title") : (q.delete_block_reason || t("quotes_page.delete_quote_blocked"))}
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

      {/* ── Pagination Controls Bar ── */}
      {!isLoading && !error && totalCount > 0 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-surface border border-border p-4 rounded-xl text-sm">
          {/* Info text & Page Size Selector */}
          <div className="flex items-center gap-4 text-text-muted">
            <span>
              {totalCount === 0 
                ? t("quotes_page.no_records") 
                : t("quotes_page.records_showing", { start: (page - 1) * pageSize + 1, end: Math.min(page * pageSize, totalCount), total: totalCount })}
            </span>
            <div className="flex items-center gap-2 border-l border-border pl-4">
              <span className="text-xs">{t("quotes_page.per_page")}</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
                className="bg-bg border border-border text-text-primary text-xs rounded-md px-2 py-1 focus:outline-none focus:border-primary cursor-pointer"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
            </div>
          </div>

          {/* Navigation Buttons */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-surface-elevated text-text-primary text-xs font-medium hover:bg-border disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={14} />
              {t("quotes_page.pagination.prev")}
            </button>

            {/* Page number buttons */}
            <div className="flex items-center gap-1 mx-1">
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter((p) => {
                  return (
                    p === 1 ||
                    p === totalPages ||
                    (p >= page - 1 && p <= page + 1)
                  );
                })
                .map((p, idx, arr) => {
                  const prev = arr[idx - 1];
                  const showEllipsis = prev && p - prev > 1;
                  return (
                    <React.Fragment key={p}>
                      {showEllipsis && (
                        <span className="px-1 text-xs text-text-muted">...</span>
                      )}
                      <button
                        onClick={() => setPage(p)}
                        className={`w-7 h-7 rounded-md text-xs font-medium flex items-center justify-center transition-colors ${
                          page === p
                            ? "bg-primary text-white shadow-sm"
                            : "bg-surface-elevated text-text-muted hover:text-text-primary hover:bg-border"
                        }`}
                      >
                        {p}
                      </button>
                    </React.Fragment>
                  );
                })}
            </div>

            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || totalPages === 0}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-surface-elevated text-text-primary text-xs font-medium hover:bg-border disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {t("quotes_page.pagination.next")}
              <ChevronRight size={14} />
            </button>
          </div>
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
                <h3 className="text-base font-semibold text-text-primary">{t("quotes_page.delete_rfq_title")}</h3>
              </div>

              <p className="text-sm text-text-muted">
                {t("quotes_page.delete_rfq_warning")}
              </p>

              <div className="mt-4 p-3.5 rounded-lg bg-bg border border-border">
                <span className="font-mono text-xs text-text-muted">#RFQ-{rfqToDelete.id.slice(0, 8).toUpperCase()}</span>
                <p className="text-sm font-semibold text-text-primary mt-0.5">{rfqToDelete.title}</p>
                <div className="flex items-center gap-2 mt-2 text-xs text-text-secondary">
                  <span>{t("quotes_page.quotes_count", { count: rfqToDelete.quotes_count ?? 0 })}</span>
                  <span>•</span>
                  <span>{t("quotes_page.target_budget", { budget: rfqToDelete.budget ? fmtCurrency(rfqToDelete.budget, "TRY", locale) : "-" })}</span>
                </div>
              </div>

              <div className="mt-3 text-xs text-amber-400/90 bg-amber-500/10 border border-amber-500/20 p-2.5 rounded-md">
                {t("quotes_page.delete_rfq_caution")}
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
                {t("quotes_page.cancel_btn")}
              </button>
              <button
                onClick={confirmDeleteRfq}
                disabled={isDeleting}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isDeleting && <Loader2 size={13} className="animate-spin" />}
                {isDeleting ? t("quotes_page.deleting") : t("quotes_page.confirm_delete_rfq_btn")}
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
                <h3 className="text-base font-semibold text-text-primary">{t("quotes_page.delete_quote_title")}</h3>
              </div>

              <p className="text-sm text-text-muted">
                {t("quotes_page.delete_quote_confirm", { supplier: quoteToDelete.quote.supplier_name || quoteToDelete.quote.extracted_supplier_name || "Supplier" })}
              </p>

              <div className="mt-4 p-3.5 rounded-lg bg-bg border border-border">
                <p className="text-sm font-semibold text-text-primary">
                  {quoteToDelete.quote.supplier_name || quoteToDelete.quote.extracted_supplier_name || t("quotes_page.table_supplier")}
                </p>
                <div className="flex items-center gap-2 mt-2 text-xs text-text-secondary">
                  <span className="font-semibold text-emerald-400">
                    {fmtCurrency(Number(quoteToDelete.quote.total_price), quoteToDelete.quote.currency, locale)}
                  </span>
                  <span>•</span>
                  <span>{quoteToDelete.quote.delivery_days ? t("rfq_detail.days_unit", { count: quoteToDelete.quote.delivery_days }) : "-"}</span>
                </div>
              </div>

              <div className="mt-3 text-xs text-text-muted bg-surface-elevated p-2.5 rounded-md border border-border">
                {t("quotes_page.delete_quote_caution")}
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
                {t("quotes_page.cancel_btn")}
              </button>
              <button
                onClick={confirmDeleteQuote}
                disabled={isDeleting}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isDeleting && <Loader2 size={13} className="animate-spin" />}
                {isDeleting ? t("quotes_page.deleting") : t("quotes_page.confirm_delete_quote_btn")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Create New RFQ ────────────────────────────────────────── */}
      {isCreateOpen && (
        <div 
          onClick={resetCreateModal}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm cursor-pointer"
        >
          <div 
            onClick={(e) => e.stopPropagation()}
            className="bg-surface border border-border rounded-xl shadow-2xl max-w-xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150 cursor-default"
          >
            <div className="p-6 border-b border-border flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-text-primary">{t("quotes_page.create_modal_title")}</h3>
                <p className="text-xs text-text-muted mt-0.5">{t("quotes_page.create_modal_subtitle")}</p>
              </div>
              <button 
                onClick={resetCreateModal}
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
                <label className="text-xs font-semibold text-text-primary">{t("quotes_page.create_modal_title_label")} *</label>
                <input
                  type="text"
                  placeholder={t("quotes_page.create_modal_title_placeholder")}
                  value={createTitle}
                  onChange={(e) => setCreateTitle(e.target.value)}
                  className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-text-primary">{t("quotes_page.create_modal_desc_label")}</label>
                <textarea
                  placeholder={t("quotes_page.create_modal_desc_placeholder")}
                  rows={2}
                  value={createDescription}
                  onChange={(e) => setCreateDescription(e.target.value)}
                  className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                />
              </div>

              {/* Items Section */}
              <div className="space-y-2 pt-2 border-t border-border">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-text-primary uppercase tracking-wider">{t("quotes_page.create_modal_items_title")}</label>
                  <button 
                    type="button"
                    onClick={() => setCreateItems(prev => [...prev, { description: "", quantity: "1", unit: "Adet" }])}
                    className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
                  >
                    <Plus size={13} /> {t("quotes_page.create_modal_add_item")}
                  </button>
                </div>

                <div className="space-y-2">
                  {createItems.map((item, idx) => (
                    <div key={idx} className="flex gap-2 items-center">
                      <input 
                        type="text" 
                        placeholder={t("quotes_page.create_modal_item_desc_placeholder")}
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
                  <label className="text-xs font-medium text-text-secondary">{t("quotes_page.create_modal_budget_label")}</label>
                  <input 
                    type="number"
                    placeholder={t("quotes_page.create_modal_budget_placeholder")}
                    value={createBudget}
                    onChange={(e) => setCreateBudget(e.target.value)}
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-text-secondary">{t("quotes_page.create_modal_max_delivery_label")}</label>
                  <input 
                    type="number"
                    placeholder={t("quotes_page.create_modal_delivery_placeholder")}
                    value={createMaxDeliveryDays}
                    onChange={(e) => setCreateMaxDeliveryDays(e.target.value)}
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-text-secondary">{t("quotes_page.create_modal_min_warranty_label")}</label>
                  <input 
                    type="number"
                    placeholder={t("quotes_page.create_modal_warranty_placeholder")}
                    value={createMinWarrantyMonths}
                    onChange={(e) => setCreateMinWarrantyMonths(e.target.value)}
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-text-secondary">{t("quotes_page.create_modal_payment_terms_label")}</label>
                  <input 
                    type="text"
                    placeholder={t("quotes_page.create_modal_payment_placeholder")}
                    value={createPaymentTerms}
                    onChange={(e) => setCreatePaymentTerms(e.target.value)}
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                  />
                </div>
              </div>
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button 
                onClick={resetCreateModal}
                disabled={isCreating}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                {t("quotes_page.cancel_btn")}
              </button>
              <button 
                onClick={handleCreateRfq}
                disabled={isCreating || !createTitle.trim()}
                className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-xs font-medium transition-colors shadow-sm disabled:opacity-50"
              >
                {isCreating && <Loader2 size={13} className="animate-spin" />}
                {isCreating ? t("quotes_page.create_modal_submitting") : t("quotes_page.create_modal_submit")}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
