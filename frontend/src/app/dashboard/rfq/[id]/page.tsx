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
  Clock,
  Truck,
  PackageCheck,
  AlertCircle,
  Calendar,
  DollarSign,
  Copy,
  ChevronRight
} from "lucide-react";
import { rfqsApi } from "@/lib/api/rfqs";
import { ordersApi } from "@/lib/api/orders";
import { 
  RFQ, 
  Quote, 
  AnalysisResponse, 
  TCOResultResponse, 
  ComplianceCheckResponse, 
  EvidenceItemResponse, 
  PurchaseOrderResponse,
  POQualityIssueResponse,
  ReviewResponse,
  EmailDeliveryResponse
} from "@/lib/api/types";
import { ComparisonMatrix } from "@/components/analysis/ComparisonMatrix";
import { EvidencePanel } from "@/components/analysis/EvidencePanel";
import { StaleNoticeBanner } from "@/components/analysis/StaleNoticeBanner";
import { ReviewModal } from "@/components/analysis/ReviewModal";
import { SupplierPerformanceDrawer } from "@/components/analysis/SupplierPerformanceDrawer";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency as fmtCurrency, formatDate as fmtDate, formatNumber as fmtNumber } from "@/lib/i18n/formatters";
import { getLocalizedApiError } from "@/lib/i18n/apiErrorMap";

export default function RFQDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const { t, locale } = useTranslation();
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

  // Deliver PO states
  const [poToDeliver, setPoToDeliver] = useState<PurchaseOrderResponse | null>(null);
  const [deliverDate, setDeliverDate] = useState("");
  const [deliverNotes, setDeliverNotes] = useState("");
  const [isDeliveringPo, setIsDeliveringPo] = useState(false);
  const [deliverPoError, setDeliverPoError] = useState<string | null>(null);

  // Complete PO states
  const [poToComplete, setPoToComplete] = useState<PurchaseOrderResponse | null>(null);
  const [finalAmount, setFinalAmount] = useState<string>("");
  const [completionNotes, setCompletionNotes] = useState("");
  const [isCompletingPo, setIsCompletingPo] = useState(false);
  const [completePoError, setCompletePoError] = useState<string | null>(null);

  // Quality Issue states
  const [poForQuality, setPoForQuality] = useState<PurchaseOrderResponse | null>(null);
  const [qualityIssueType, setQualityIssueType] = useState("defect");
  const [qualitySeverity, setQualitySeverity] = useState("medium");
  const [qualityRejectionCount, setQualityRejectionCount] = useState<number>(0);
  const [qualityDescription, setQualityDescription] = useState("");
  const [isSavingQuality, setIsSavingQuality] = useState(false);
  const [qualityError, setQualityError] = useState<string | null>(null);

  // Quality Issues loaded for POs
  const [poQualityIssuesMap, setPoQualityIssuesMap] = useState<Record<string, POQualityIssueResponse[]>>({});
  const [expandedPoQuality, setExpandedPoQuality] = useState<Record<string, boolean>>({});

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
  const [suppliers, setSuppliers] = useState<{ id: string; name: string; email?: string | null }[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadWarning, setUploadWarning] = useState<string | null>(null);

  // Phase 9: RFQ Invitations & Outbox State
  const [invitations, setInvitations] = useState<EmailDeliveryResponse[]>([]);
  const [isLoadingInvitations, setIsLoadingInvitations] = useState(false);
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [inviteSupplierId, setInviteSupplierId] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteCustomMessage, setInviteCustomMessage] = useState("");
  const [isSendingInvite, setIsSendingInvite] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null);
  const [retryingInvitationId, setRetryingInvitationId] = useState<string | null>(null);
  const [revokingInvitationId, setRevokingInvitationId] = useState<string | null>(null);
  const [copiedInvitationId, setCopiedInvitationId] = useState<string | null>(null);

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
      setCancelRfqError(t("rfq_detail.validation.err_cancel_reason_min"));
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
      setCancelRfqError(getLocalizedApiError(err, locale));
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
      setCancelPoError(t("rfq_detail.validation.err_cancel_reason_min"));
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
      setCancelPoError(getLocalizedApiError(err, locale));
    } finally {
      setIsCancellingPo(false);
    }
  };

  const fetchQualityIssuesForPos = async (pos: PurchaseOrderResponse[]) => {
    try {
      const issuesMap: Record<string, POQualityIssueResponse[]> = {};
      await Promise.all(
        pos.map(async (po) => {
          try {
            const issues = await ordersApi.getQualityIssues(po.id);
            issuesMap[po.id] = issues;
          } catch {
            issuesMap[po.id] = [];
          }
        })
      );
      setPoQualityIssuesMap(issuesMap);
    } catch (e) {
      console.error("Failed to load quality issues for orders", e);
    }
  };

  const handleDeliverPo = async () => {
    if (!poToDeliver) return;
    try {
      setIsDeliveringPo(true);
      setDeliverPoError(null);
      await ordersApi.deliverOrder(poToDeliver.id, {
        actual_delivery_date: deliverDate || undefined,
        delivery_notes: deliverNotes.trim() || undefined,
      });
      const updatedPos = await rfqsApi.getPurchaseOrders(rfqId);
      setPurchaseOrders(updatedPos);
      await fetchQualityIssuesForPos(updatedPos);
      setPoToDeliver(null);
      setDeliverDate("");
      setDeliverNotes("");
    } catch (err: any) {
      setDeliverPoError(getLocalizedApiError(err, locale));
    } finally {
      setIsDeliveringPo(false);
    }
  };

  const handleCompletePo = async () => {
    if (!poToComplete) return;
    try {
      setIsCompletingPo(true);
      setCompletePoError(null);
      const parsedAmount = finalAmount !== "" ? parseFloat(finalAmount) : undefined;
      await ordersApi.completeOrder(poToComplete.id, {
        final_amount: parsedAmount,
        completion_notes: completionNotes.trim() || undefined,
      });
      const updatedPos = await rfqsApi.getPurchaseOrders(rfqId);
      setPurchaseOrders(updatedPos);
      await fetchQualityIssuesForPos(updatedPos);
      setPoToComplete(null);
      setFinalAmount("");
      setCompletionNotes("");
    } catch (err: any) {
      setCompletePoError(getLocalizedApiError(err, locale));
    } finally {
      setIsCompletingPo(false);
    }
  };

  const handleSaveQualityIssue = async () => {
    if (!poForQuality) return;
    if (!qualityDescription.trim() || qualityDescription.trim().length < 3) {
      setQualityError(t("rfq_detail.validation.err_quality_desc_min"));
      return;
    }
    try {
      setIsSavingQuality(true);
      setQualityError(null);
      await ordersApi.addQualityIssue(poForQuality.id, {
        issue_type: qualityIssueType,
        severity: qualitySeverity,
        description: qualityDescription.trim(),
        rejection_count: Number(qualityRejectionCount) || 0,
      });
      const updatedPos = await rfqsApi.getPurchaseOrders(rfqId);
      setPurchaseOrders(updatedPos);
      await fetchQualityIssuesForPos(updatedPos);
      setPoForQuality(null);
      setQualityDescription("");
      setQualityRejectionCount(0);
      setQualityIssueType("defect");
      setQualitySeverity("medium");
    } catch (err: any) {
      setQualityError(getLocalizedApiError(err, locale));
    } finally {
      setIsSavingQuality(false);
    }
  };

  const handleDeleteRfq = async () => {
    try {
      setIsDeleting(true);
      setDeleteError(null);
      await rfqsApi.deleteRfq(rfqId);
      router.push("/dashboard/quotes");
    } catch (err: any) {
      setDeleteError(getLocalizedApiError(err, locale));
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
      setDeleteError(getLocalizedApiError(err, locale));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCreateSupplier = async () => {
    if (!newSupplierName.trim()) {
      setSupplierCreateError(t("rfq_detail.validation.err_supplier_name_required"));
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
      setSupplierCreateError(getLocalizedApiError(err, locale));
    } finally {
      setIsSavingSupplier(false);
    }
  };

  const handleUploadSupplierQuote = async () => {
    if (!uploadFile || !uploadSupplierId) {
      setUploadError(t("rfq_detail.validation.err_file_and_supplier_required"));
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
      console.error("Quote upload error:", err);
      if (err?.message?.includes("Authentication credentials") || err?.status === 401) {
        setUploadError(t("rfq_detail.validation.err_session_expired"));
      } else {
        setUploadError(getLocalizedApiError(err, locale));
      }
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
      setAnalysisError(getLocalizedApiError(err, locale));
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
      if (poRes.status === "fulfilled") {
        setPurchaseOrders(poRes.value);
        fetchQualityIssuesForPos(poRes.value);
      }
      if (analysisRes.status === "fulfilled") setAnalysis(analysisRes.value);
      if (quotesRes.status === "fulfilled") setQuotes(quotesRes.value);
    });
  };

  const fetchInvitations = async () => {
    try {
      setIsLoadingInvitations(true);
      const res = await rfqsApi.getRfqInvitations(rfqId);
      setInvitations(res);
    } catch (err) {
      console.error("Failed to load invitations:", err);
    } finally {
      setIsLoadingInvitations(false);
    }
  };

  const handleSendInvitation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) {
      setInviteError(t("rfq_detail.validation.err_email_invalid"));
      return;
    }
    try {
      setIsSendingInvite(true);
      setInviteError(null);
      setInviteSuccess(null);
      const res = await rfqsApi.sendRfqInvitation(rfqId, {
        recipient_email: inviteEmail.trim(),
        supplier_id: inviteSupplierId || undefined,
        recipient_name: inviteName.trim() || undefined,
        custom_message: inviteCustomMessage.trim() || undefined,
      });
      setInviteSuccess(t("rfq_detail.invitations_section.invite_queued_success", { email: res.recipient_email, status: res.status }));
      setIsInviteModalOpen(false);
      setInviteEmail("");
      setInviteName("");
      setInviteCustomMessage("");
      setInviteSupplierId("");
      await fetchInvitations();
    } catch (err: any) {
      setInviteError(getLocalizedApiError(err, locale));
    } finally {
      setIsSendingInvite(false);
    }
  };

  const handleRetryInvitation = async (invitationId: string) => {
    try {
      setRetryingInvitationId(invitationId);
      await rfqsApi.retryRfqInvitation(rfqId, invitationId);
      await fetchInvitations();
    } catch (err: any) {
      alert(`Davet yeniden denenirken hata oluştu: ${err.message || err}`);
    } finally {
      setRetryingInvitationId(null);
    }
  };

  const handleRevokeInvitation = async (invitationId: string) => {
    if (!confirm(t("rfq_detail.validation.confirm_revoke_invite"))) {
      return;
    }
    try {
      setRevokingInvitationId(invitationId);
      await rfqsApi.revokeRfqInvitation(rfqId, invitationId);
      await fetchInvitations();
    } catch (err: any) {
      alert(`Davet iptal edilirken hata oluştu: ${err.message || err}`);
    } finally {
      setRevokingInvitationId(null);
    }
  };

  const handleCopyPortalLink = async (invitationId: string, portalUrl?: string | null) => {
    if (!portalUrl) return;
    try {
      const fullUrl = portalUrl.startsWith("http") ? portalUrl : `${window.location.origin}${portalUrl}`;
      await navigator.clipboard.writeText(fullUrl);
      setCopiedInvitationId(invitationId);
      setTimeout(() => setCopiedInvitationId(null), 2000);
    } catch (err) {
      console.error("Failed to copy portal URL:", err);
    }
  };

  useEffect(() => {
    async function loadData() {
      try {
        setIsLoading(true);
        const [rfqRes, quotesRes, analysisRes, poRes, invRes] = await Promise.allSettled([
          rfqsApi.getRfq(rfqId),
          rfqsApi.getRfqQuotes(rfqId),
          rfqsApi.getAnalysis(rfqId),
          rfqsApi.getPurchaseOrders(rfqId),
          rfqsApi.getRfqInvitations(rfqId),
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

        if (invRes.status === 'fulfilled') {
          setInvitations(invRes.value);
        }

        if (poRes.status === 'fulfilled') {
          setPurchaseOrders(poRes.value);
          fetchQualityIssuesForPos(poRes.value);
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
        <h2 className="text-xl font-semibold">{t("rfq_detail.error_loading_title")}</h2>
        <p className="text-sm font-medium">{error || "RFQ not found."}</p>
        <button onClick={handleBack} className="text-sm text-primary hover:underline mt-4">{t("rfq_detail.header.back_to_quotes")}</button>
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

  // Active PO detection
  const activePos = purchaseOrders.filter(p => p.status !== 'cancelled');
  const hasActivePo = activePos.length > 0;
  const firstActivePo = activePos[0] || null;

  // Policy Warnings count
  const warningsCount = analysis?.compliance_checks?.filter(c => c.result !== 'pass').length || 0;

  return (
    <div className="flex flex-col gap-6">
      
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button 
            onClick={handleBack}
            title={t("rfq_detail.header.back_to_quotes")}
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
                  {t("rfq_detail.header.archived_badge")}
                </span>
              )}
            </div>
            <p className="text-sm text-text-muted mt-1">{fmtDate(rfq.created_at, locale)}</p>
          </div>
        </div>
        
        <div className="flex items-center gap-2.5 flex-wrap">
          {rfq.status !== 'cancelled' && (
            <button 
              onClick={() => setIsUploadQuoteOpen(true)}
              className="flex items-center gap-2 bg-surface-elevated border border-border hover:bg-bg text-primary px-3.5 py-2 rounded text-xs font-medium transition-colors shadow-sm"
            >
              <Plus size={15} />
              {t("rfq_detail.actions.upload_quote")}
            </button>
          )}

          {rfq.status !== 'cancelled' && (
            <button
              onClick={() => setIsInviteModalOpen(true)}
              className="flex items-center gap-2 bg-surface-elevated border border-border hover:bg-bg text-blue-600 dark:text-blue-400 px-3.5 py-2 rounded text-xs font-medium transition-colors shadow-sm"
            >
              <Mail size={15} />
              {t("rfq_detail.actions.invite_supplier")}
            </button>
          )}

          {/* Multi-Analysis Action Button */}
          {rfq.status !== 'cancelled' && (
            <button
              onClick={handleRunAnalysis}
              disabled={isAnalyzing || quotes.length < 2}
              title={
                quotes.length < 2
                  ? t("rfq_detail.header.analyze_tooltip_min")
                  : hasActivePo
                  ? t("rfq_detail.header.analyze_tooltip_po", { po: firstActivePo?.po_number || "" })
                  : analysis
                  ? t("rfq_detail.header.analyze_tooltip_update")
                  : t("rfq_detail.header.analyze_tooltip_start")
              }
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded text-xs font-semibold transition-colors shadow-sm ${
                quotes.length < 2
                  ? "bg-surface border border-border text-text-muted opacity-50 cursor-not-allowed"
                  : isAnalyzing
                  ? "bg-primary/20 text-primary border border-primary/40 cursor-wait"
                  : hasActivePo && !analysis?.is_stale
                  ? "bg-surface-elevated border border-border hover:bg-bg text-text-secondary"
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
                    {hasActivePo
                      ? analysis?.is_stale
                        ? t("rfq_detail.header.btn_analyze_new_rules")
                        : t("rfq_detail.header.btn_re_evaluate")
                      : analysis
                      ? t("rfq_detail.actions.recalculate")
                      : t("rfq_detail.header.btn_start_multi_analysis")}
                    {quotes.length < 2 && ` (${quotes.length}/2)`}
                  </span>
                </>
              )}
            </button>
          )}

          {/* Review & Decision Action */}
          {analysis && rfq.status !== 'cancelled' && !hasActivePo && (
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
              title={t("rfq_detail.header.unarchive_title")}
              className="flex items-center gap-1.5 px-3 py-2 rounded bg-surface-elevated border border-border hover:bg-bg text-xs font-medium text-text-secondary transition-colors"
            >
              <ArchiveRestore size={14} />
              {t("rfq_detail.header.unarchive_btn")}
            </button>
          ) : (
            <button
              onClick={handleArchiveRfq}
              disabled={isArchiving}
              title={t("rfq_detail.header.archive_title")}
              className="flex items-center gap-1.5 px-3 py-2 rounded bg-surface-elevated border border-border hover:bg-bg text-xs font-medium text-text-muted hover:text-text-primary transition-colors"
            >
              <Archive size={14} />
              {t("rfq_detail.header.archive_btn")}
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
              title={t("rfq_detail.header.cancel_title")}
              className="flex items-center gap-1.5 px-3 py-2 rounded border border-amber-500/30 text-amber-500 hover:bg-amber-500/10 text-xs font-medium transition-colors"
            >
              <Ban size={14} />
              {t("rfq_detail.header.cancel_btn")}
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
            title={rfq.can_delete ? t("rfq_detail.header.delete_title") : (rfq.delete_block_reason || t("rfq_detail.header.delete_blocked"))}
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
          hasActivePo={hasActivePo}
          poNumber={firstActivePo?.po_number}
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
            <span className="text-text-muted block">{t("rfq_detail.target_budget")}</span>
            <span className="font-semibold text-text-primary mt-0.5 block">
              {rfq.budget ? fmtCurrency(rfq.budget, 'TRY', locale) : 'Not specified'}
            </span>
          </div>
          <div>
            <span className="text-text-muted block">{t("rfq_detail.max_delivery")}</span>
            <span className="font-semibold text-text-primary mt-0.5 block">
              {rfq.max_delivery_days ? `${rfq.max_delivery_days} days` : 'Not specified'}
            </span>
          </div>
          <div>
            <span className="text-text-muted block">{t("rfq_detail.min_warranty")}</span>
            <span className="font-semibold text-text-primary mt-0.5 block">
              {rfq.min_warranty_months ? `${rfq.min_warranty_months} months` : 'Not specified'}
            </span>
          </div>
          <div>
            <span className="text-text-muted block">{t("rfq_detail.payment_terms")}</span>
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
                {t("rfq_detail.quotes_section.pending_comparison_title")}
              </h3>
              <p className="text-xs text-text-muted mt-0.5">
                {t("rfq_detail.quotes_section.pending_comparison_desc")}
              </p>
            </div>
          </div>
          {rfq.status !== "cancelled" && (
            <button
              onClick={() => setIsUploadQuoteOpen(true)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary hover:bg-primary-hover text-white transition-colors shrink-0"
            >
              {t("rfq_detail.quotes_section.btn_upload_second_quote")}
            </button>
          )}
        </div>
      ) : (
        <div className="p-8 rounded-xl bg-surface-elevated border-2 border-dashed border-border text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-surface border border-border text-text-muted mx-auto flex items-center justify-center">
            <UploadCloud size={20} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">{t("rfq_detail.quotes_section.empty_quotes_title")}</h3>
            <p className="text-xs text-text-muted mt-1 max-w-sm mx-auto">
              {t("rfq_detail.quotes_section.empty_quotes_desc")}
            </p>
          </div>
          {rfq.status !== "cancelled" && (
            <button
              onClick={() => setIsUploadQuoteOpen(true)}
              className="px-4 py-2 rounded-lg text-xs font-semibold bg-primary hover:bg-primary-hover text-white transition-colors inline-flex items-center gap-1.5"
            >
              <Plus size={14} />
              {t("rfq_detail.quotes_section.btn_add_first_quote")}
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
                  <th className="px-4 py-3 font-medium">{t("quotes_page.table_supplier")}</th>
                  <th className="px-4 py-3 font-medium">{t("quotes_page.table_total_price")}</th>
                  <th className="px-4 py-3 font-medium">{t("quotes_page.table_delivery")}</th>
                  <th className="px-4 py-3 font-medium">{t("quotes_page.table_warranty")}</th>
                  <th className="px-4 py-3 font-medium">{t("rfq_detail.table_status")}</th>
                  <th className="px-4 py-3 font-medium text-right">{t("quotes_page.table_action")}</th>
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
                            onClick={() => setDrawerSupplier({ id: q.supplier_id, name: q.supplier_name || 'Supplier' })}
                            title={t("rfq_detail.quotes_section.supplier_scorecard_tooltip")}
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
                            title={q.can_delete ? t("quotes_page.delete_quote_title") : (q.delete_block_reason || t("rfq_detail.quotes_section.delete_quote_blocked"))}
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
                    <div className="text-xs text-text-muted mb-1">{t("quotes_page.table_supplier")}</div>
                    <div className="text-sm font-medium text-text-primary">{displayQuote.supplier_name || displayQuote.supplier_id}</div>
                  </div>
                  <div>
                    <div className="text-xs text-text-muted mb-1">{t("quotes_page.table_payment")}</div>
                    <div className="text-sm font-medium text-text-primary">{displayQuote.payment_terms || 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-text-muted mb-1">{t("rfq_detail.delivery_time")}</div>
                    <div className="text-sm font-medium text-text-primary">{displayQuote.delivery_days ? `${displayQuote.delivery_days} Days` : 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-text-muted mb-1">{t("quotes_page.table_warranty")}</div>
                    <div className="text-sm font-medium text-text-primary">{displayQuote.warranty_months ? `${displayQuote.warranty_months} Months` : 'N/A'}</div>
                  </div>
                </div>

                {/* Line Items Table */}
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-bg text-text-muted text-xs uppercase border-b border-border">
                      <tr>
                        <th className="px-4 py-3 font-medium">{t("rfq_detail.item_description")}</th>
                        <th className="px-4 py-3 font-medium text-right">{t("rfq_detail.qty")}</th>
                        <th className="px-4 py-3 font-medium text-right">{t("rfq_detail.unit_price")}</th>
                        <th className="px-4 py-3 font-medium text-right">{t("rfq_detail.total")}</th>
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
                    <span>{t("rfq_detail.subtotal_label")}</span>
                    <span>₺ {displayQuote.subtotal?.toLocaleString('en-US') || 0}</span>
                  </div>
                  {displayQuote.discount_amount != null && displayQuote.discount_amount > 0 && (
                    <div className="flex justify-between w-64 text-text-muted">
                      <span>{t("rfq_detail.discount_label")}</span>
                      <span className="text-success">- ₺ {displayQuote.discount_amount.toLocaleString('en-US')}</span>
                    </div>
                  )}
                  <div className="flex justify-between w-64 text-text-muted border-b border-border pb-2">
                    <span>
                      VAT ({displayQuote.vat_rate != null ? `${(displayQuote.vat_rate * 100).toFixed(0)}%` : t("rfq_detail.quotes_section.vat_not_specified")}):
                    </span>
                    <span>
                      {displayQuote.vat_amount != null
                        ? `₺ ${displayQuote.vat_amount.toLocaleString('en-US')}`
                        : "[Eksik Veri]"}
                    </span>
                  </div>
                  <div className="flex justify-between w-64 font-semibold text-text-primary text-base pt-1">
                    <span>{t("rfq_detail.total_quote_label")}</span>
                    <span>₺ {displayQuote.total_price?.toLocaleString('en-US') || 0}</span>
                  </div>
                  
                  {displayTCO && (
                    <>
                      <div className="flex justify-between w-64 font-semibold text-amber-500 text-base pt-2 border-t border-border mt-2">
                        <span>{t("rfq_detail.computed_tco_label")}</span>
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
                const isDelivered = po.status === 'delivered';
                const isCompleted = po.status === 'completed';
                const isIssued = po.status === 'issued';
                const isDraft = po.status === 'draft';
                const poQuote = quotes.find(q => q.id === po.quote_id);
                const issues = poQualityIssuesMap[po.id] || [];
                const isQualityExpanded = !!expandedPoQuality[po.id];

                let delayText: string | null = null;
                let delayBadgeClass = "bg-zinc-800 text-zinc-300";
                if (po.expected_delivery_date && po.actual_delivery_date) {
                  const exp = new Date(po.expected_delivery_date).getTime();
                  const act = new Date(po.actual_delivery_date).getTime();
                  const diffDays = Math.round((act - exp) / (1000 * 60 * 60 * 24));
                  if (diffDays > 0) {
                    delayText = t("rfq_detail.orders_section.delay_late", { days: diffDays });
                    delayBadgeClass = "bg-red-500/15 text-red-400 border border-red-500/30";
                  } else if (diffDays < 0) {
                    delayText = t("rfq_detail.orders_section.delay_early", { days: Math.abs(diffDays) });
                    delayBadgeClass = "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30";
                  } else {
                    delayText = t("rfq_detail.orders_section.delay_on_time");
                    delayBadgeClass = "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30";
                  }
                } else if (po.expected_delivery_date && !po.actual_delivery_date && !isPoCancelled) {
                  const exp = new Date(po.expected_delivery_date).getTime();
                  const now = new Date().getTime();
                  if (now > exp) {
                    const overDays = Math.round((now - exp) / (1000 * 60 * 60 * 24));
                    delayText = t("rfq_detail.orders_section.delay_overdue", { days: overDays });
                    delayBadgeClass = "bg-amber-500/15 text-amber-400 border border-amber-500/30";
                  }
                }

                const cardBorderClass = isPoCancelled
                  ? 'bg-red-950/20 border-red-500/30'
                  : isCompleted
                  ? 'bg-emerald-950/20 border-emerald-500/30'
                  : isDelivered
                  ? 'bg-amber-950/20 border-amber-500/30'
                  : isDraft
                  ? 'bg-amber-950/20 border-amber-500/30'
                  : 'bg-primary/5 border-primary/30';

                const statusBadgeClass = isPoCancelled
                  ? 'bg-red-500/20 text-red-300 border-red-500/40'
                  : isCompleted
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                  : isDelivered
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : isDraft
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : 'bg-primary/20 text-primary-light border-primary/40';

                return (
                  <div 
                    key={po.id} 
                    className={`rounded-xl p-5 shadow-sm border text-text-primary ${cardBorderClass}`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <h2 className="text-sm font-semibold uppercase tracking-wider flex items-center gap-2">
                        {isPoCancelled ? (
                          <>
                            <Ban size={16} className="text-red-400" />
                            <span className="text-red-400">{t("rfq_detail.orders_section.status_cancelled")}</span>
                          </>
                        ) : isCompleted ? (
                          <>
                            <PackageCheck size={16} className="text-emerald-400" />
                            <span className="text-emerald-400">{t("rfq_detail.orders_section.status_completed")}</span>
                          </>
                        ) : isDelivered ? (
                          <>
                            <Truck size={16} className="text-amber-400" />
                            <span className="text-amber-400">{t("rfq_detail.orders_section.status_delivered")}</span>
                          </>
                        ) : isDraft ? (
                          <>
                            <Clock size={16} className="text-amber-400" />
                            <span className="text-amber-400">{t("rfq_detail.orders_section.status_draft_threshold")}</span>
                          </>
                        ) : (
                          <>
                            <CheckCircle size={16} className="text-primary" />
                            <span className="text-primary-light">{t("rfq_detail.orders_section.status_approved_sent")}</span>
                          </>
                        )}
                      </h2>
                      <span className={`px-2.5 py-0.5 rounded text-[11px] font-mono font-semibold border ${statusBadgeClass}`}>
                        {po.status.toUpperCase()}
                      </span>
                    </div>

                    {isDraft && (
                      <div className="mb-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 font-semibold text-amber-400">
                            <AlertTriangle size={14} className="shrink-0" />
                            <span>{t("rfq_detail.orders_section.pending_authority_banner_title")}</span>
                          </div>
                          <Link
                            href="/dashboard/approvals"
                            className="inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 transition-colors"
                          >
                            <span>{t("rfq_detail.orders_section.pending_authority_go_to_queue")}</span>
                            <ChevronRight size={12} />
                          </Link>
                        </div>
                        <p className="text-[11px] text-text-muted leading-relaxed">
                          {t("rfq_detail.orders_section.pending_authority_desc")}
                        </p>
                      </div>
                    )}

                    <div className="bg-bg/60 rounded p-3 text-xs font-mono space-y-1.5 border border-border">
                      <div className="flex justify-between">
                        <span className="text-text-muted">{t("rfq_detail.po_number_label")}</span>
                        <span className="font-semibold text-text-primary">{po.po_number}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">{t("rfq_detail.orders_section.label_selected_quote")}</span>
                        <span className="font-semibold text-text-primary">{poQuote?.supplier_name || po.quote_id.slice(0, 8)}</span>
                      </div>
                      {poQuote && (
                        <div className="flex justify-between">
                          <span className="text-text-muted">{t("rfq_detail.orders_section.label_order_amount")}</span>
                          <span className="font-semibold text-text-primary">
                            {new Intl.NumberFormat('tr-TR', { style: 'currency', currency: poQuote.currency || 'TRY' }).format(poQuote.total_price)}
                          </span>
                        </div>
                      )}
                      <div className="flex justify-between">
                        <span className="text-text-muted">{t("rfq_detail.orders_section.label_created_at")}</span>
                        <span>{new Date(po.created_at).toLocaleDateString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">{t("rfq_detail.expected_delivery_label")}</span>
                        <span>{po.expected_delivery_date || "-"}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-text-muted">Fiilî Teslimat:</span>
                        <div className="flex items-center gap-2">
                          <span>{po.actual_delivery_date || "-"}</span>
                          {delayText && (
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-sans font-medium ${delayBadgeClass}`}>
                              {delayText}
                            </span>
                          )}
                        </div>
                      </div>
                      {po.final_amount != null && (
                        <div className="flex justify-between text-emerald-400 pt-1 border-t border-border">
                          <span className="text-text-muted">{t("rfq_detail.orders_section.label_final_amount")}</span>
                          <span className="font-semibold">₺ {Number(po.final_amount).toLocaleString('tr-TR')}</span>
                        </div>
                      )}
                      {po.delivery_notes && (
                        <div className="pt-1 text-text-secondary text-[11px] border-t border-border">
                          <span className="text-text-muted block text-[10px] uppercase font-semibold">{t("rfq_detail.notes_label")}</span>
                          <span className="block mt-0.5 whitespace-pre-line">{po.delivery_notes}</span>
                        </div>
                      )}
                      {isPoCancelled && (
                        <div className="pt-1 text-red-300 text-xs border-t border-border">
                          <span className="text-text-muted block text-[10px] uppercase font-semibold">{t("rfq_detail.orders_section.label_cancellation_reason", { by: po.cancelled_at ? fmtDate(po.cancelled_at, locale) : "-" })}</span>
                          <span className="italic block mt-0.5">{po.cancellation_reason || t("rfq_detail.orders_section.reason_unspecified")}</span>
                        </div>
                      )}
                    </div>

                    {/* Quality Issues Summary & Accordion */}
                    <div className="mt-3 pt-2.5 border-t border-border/60">
                      <div className="flex items-center justify-between text-xs">
                        <button
                          type="button"
                          onClick={() => setExpandedPoQuality(prev => ({ ...prev, [po.id]: !prev[po.id] }))}
                          className="flex items-center gap-1.5 font-medium text-text-secondary hover:text-text-primary transition-colors"
                        >
                          <AlertCircle size={13} className={issues.length > 0 ? "text-amber-400" : "text-text-muted"} />
                          <span>{t("rfq_detail.orders_section.quality_records_title", { count: issues.length })}</span>
                          <span className="text-[10px] text-text-muted">[{isQualityExpanded ? t("rfq_detail.orders_section.btn_hide") : t("rfq_detail.orders_section.btn_show")}]</span>
                        </button>

                        {!isPoCancelled && (
                          <button
                            type="button"
                            onClick={() => {
                              setPoForQuality(po);
                              setQualityIssueType("defect");
                              setQualitySeverity("medium");
                              setQualityRejectionCount(0);
                              setQualityDescription("");
                              setQualityError(null);
                            }}
                            className="text-[11px] font-medium text-amber-400 hover:text-amber-300 transition-colors"
                          >
                            {t("rfq_detail.orders_section.btn_add_quality_record")}
                          </button>
                        )}
                      </div>

                      {isQualityExpanded && (
                        <div className="mt-2 space-y-1.5">
                          {issues.length === 0 ? (
                            <p className="text-[11px] text-text-muted italic bg-bg/40 p-2 rounded">
                              {t("rfq_detail.orders_section.empty_quality_records")}
                            </p>
                          ) : (
                            issues.map(qi => (
                              <div key={qi.id} className="p-2 rounded bg-bg/70 border border-border text-xs space-y-1">
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-1.5">
                                    <span className="font-semibold text-text-primary uppercase text-[10px] px-1.5 py-0.5 rounded bg-surface border border-border">
                                      {qi.issue_type}
                                    </span>
                                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                                      qi.severity === 'critical'
                                        ? 'bg-red-500/20 text-red-300'
                                        : qi.severity === 'medium'
                                        ? 'bg-amber-500/20 text-amber-300'
                                        : 'bg-zinc-700/50 text-zinc-300'
                                    }`}>
                                      {qi.severity}
                                    </span>
                                  </div>
                                  {qi.rejection_count > 0 && (
                                    <span className="text-[11px] font-semibold text-red-400">
                                      {t("rfq_detail.orders_section.rejection_count_label", { count: qi.rejection_count })}
                                    </span>
                                  )}
                                </div>
                                <p className="text-text-secondary text-[11px]">{qi.description}</p>
                                <div className="flex justify-between text-[10px] text-text-muted pt-0.5">
                                  <span>{t("rfq_detail.orders_section.reported_by_label", { name: qi.reported_by_name || "User" })}</span>
                                  <span>{new Date(qi.created_at).toLocaleDateString()}</span>
                                </div>
                              </div>
                            ))
                          )}
                        </div>
                      )}
                    </div>

                    {/* Actions Bar */}
                    {!isPoCancelled && (
                      <div className="mt-4 pt-3 border-t border-border flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-2">
                          {isIssued && (
                            <button
                              onClick={() => {
                                setPoToDeliver(po);
                                setDeliverDate(new Date().toISOString().split("T")[0]);
                                setDeliverNotes("");
                                setDeliverPoError(null);
                              }}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold transition-colors shadow-sm"
                            >
                              <Truck size={13} />
                              {t("rfq_detail.orders_section.btn_delivered")}
                            </button>
                          )}
                          {isDelivered && (
                            <button
                              onClick={() => {
                                setPoToComplete(po);
                                setFinalAmount(po.final_amount != null ? String(po.final_amount) : "");
                                setCompletionNotes("");
                                setCompletePoError(null);
                              }}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-colors shadow-sm"
                            >
                              <PackageCheck size={13} />
                              {t("rfq_detail.orders_section.btn_complete_order")}
                            </button>
                          )}
                        </div>

                        <button
                          onClick={() => {
                            setPoToCancel(po);
                            setPoCancelReason("");
                            setCancelPoError(null);
                          }}
                          disabled={isCompleted}
                          title={isCompleted ? t("rfq_detail.orders_section.tooltip_completed_no_cancel") : t("rfq_detail.orders_section.tooltip_cancel_po")}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                            isCompleted
                              ? "text-zinc-600 border border-zinc-800 cursor-not-allowed opacity-40"
                              : "border border-red-500/30 text-red-400 hover:bg-red-500/10"
                          }`}
                        >
                          <Ban size={13} />
                          {t("rfq_detail.orders_section.btn_cancel_order")}
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
                {t("rfq_detail.orders_section.next_step_dispatch_title")}
              </h2>
              <p className="text-xs text-slate-400 mb-4 leading-relaxed">
                {t("rfq_detail.orders_section.next_step_dispatch_desc")}
              </p>
              <div className="bg-slate-800 rounded p-3 text-xs font-mono text-slate-300 border border-slate-700">
                {t("rfq_detail.orders_section.subject_preview", { id: rfq.id.split('-')[0] })}<br/>
                {t("rfq_detail.orders_section.attached_preview", { id: rfq.id.split('-')[0] })}
              </div>
            </div>
          )}

          {/* ── Phase 9: Supplier Invitations & Outbox Deliveries ────────── */}
          <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
              <div>
                <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider flex items-center gap-2">
                  <Mail size={16} className="text-blue-500" />
                  Supplier Invitations & Email Outbox ({invitations.length})
                </h2>
                <p className="text-xs text-text-muted mt-0.5">
                  Durable background email deliveries sent to suppliers via transactional outbox.
                </p>
              </div>
              {rfq.status !== "cancelled" && (
                <button
                  onClick={() => setIsInviteModalOpen(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition-colors shrink-0"
                >
                  <Plus size={14} />
                  {t("rfq_detail.invitations_section.btn_send_new_invite")}
                </button>
              )}
            </div>

            {inviteSuccess && (
              <div className="mb-4 p-3 rounded-lg bg-green-500/10 border border-green-500/20 text-green-600 dark:text-green-400 text-xs flex items-center justify-between">
                <span>{inviteSuccess}</span>
                <button onClick={() => setInviteSuccess(null)} className="text-xs hover:underline">{t("common.actions.close")}</button>
              </div>
            )}

            {invitations.length === 0 ? (
              <div className="p-6 rounded-lg border border-dashed border-border text-center text-xs text-text-muted">
                {t("rfq_detail.invitations_section.empty_invitations")}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-surface/50 border-b border-border text-text-muted uppercase">
                    <tr>
                      <th className="px-3 py-2.5 font-medium">Recipient / Supplier</th>
                      <th className="px-3 py-2.5 font-medium">{t("rfq_detail.table_subject")}</th>
                      <th className="px-3 py-2.5 font-medium">{t("rfq_detail.table_status")}</th>
                      <th className="px-3 py-2.5 font-medium">{t("rfq_detail.table_attempts")}</th>
                      <th className="px-3 py-2.5 font-medium">{t("rfq_detail.table_date")}</th>
                      <th className="px-3 py-2.5 font-medium text-right">{t("rfq_detail.table_actions")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {invitations.map((inv) => {
                      const isFailed = inv.status === "failed";
                      const isSent = inv.status === "sent";
                      const isDelivered = inv.status === "delivered";
                      const isSending = inv.status === "sending";

                      let badgeClass = "bg-blue-500/10 text-blue-500 border-blue-500/20";
                      let badgeLabel = "Queued";
                      if (inv.is_revoked) {
                        badgeClass = "bg-zinc-500/10 text-zinc-400 border-zinc-500/20 line-through";
                        badgeLabel = t("rfq_detail.invitations_section.badge_invite_revoked");
                      } else if (inv.submitted_at || inv.submitted_quote_id) {
                        badgeClass = "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
                        badgeLabel = t("rfq_detail.invitations_section.badge_quote_received");
                      } else if (isSending) {
                        badgeClass = "bg-amber-500/10 text-amber-500 border-amber-500/20";
                        badgeLabel = "Sending...";
                      } else if (isSent) {
                        badgeClass = "bg-emerald-500/10 text-emerald-500 border-emerald-500/20";
                        badgeLabel = "Sent";
                      } else if (isDelivered) {
                        badgeClass = "bg-green-500/10 text-green-400 border-green-500/20";
                        badgeLabel = "Delivered";
                      } else if (isFailed) {
                        badgeClass = "bg-red-500/10 text-red-400 border-red-500/20";
                        badgeLabel = "Failed";
                      }

                      return (
                        <tr key={inv.id} className="hover:bg-surface/30 transition-colors">
                          <td className="px-3 py-2.5">
                            <div className="font-medium text-text-primary">{inv.recipient_email}</div>
                            {inv.recipient_name && (
                              <div className="text-[11px] text-text-muted">{inv.recipient_name}</div>
                            )}
                          </td>
                          <td className="px-3 py-2.5 max-w-xs truncate text-text-secondary" title={inv.subject}>
                            {inv.subject}
                          </td>
                          <td className="px-3 py-2.5">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${badgeClass}`}>
                              {badgeLabel}
                            </span>
                            {inv.last_error && (
                              <div className="text-[10px] text-red-400 mt-0.5 max-w-xs truncate" title={inv.last_error}>
                                {inv.last_error}
                              </div>
                            )}
                            {inv.submitted_at && (
                              <div className="text-[10px] text-emerald-400/80 mt-0.5">
                                {new Date(inv.submitted_at).toLocaleDateString()} tarihinde teklif iletildi
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-2.5 text-text-muted">
                            {inv.attempt_count} / {inv.max_attempts}
                          </td>
                          <td className="px-3 py-2.5 text-text-muted">
                            {inv.sent_at ? new Date(inv.sent_at).toLocaleString() : new Date(inv.queued_at).toLocaleString()}
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              {inv.portal_url && !inv.is_revoked && (
                                <button
                                  onClick={() => handleCopyPortalLink(inv.id, inv.portal_url)}
                                  className="px-2 py-1 rounded text-[11px] font-medium bg-surface hover:bg-surface-elevated text-text-secondary border border-border transition-colors flex items-center gap-1"
                                  title={t("rfq_detail.invitations_section.tooltip_copy_link")}
                                >
                                  {copiedInvitationId === inv.id ? (
                                    <>
                                      <Check size={12} className="text-emerald-400" />
                                      <span className="text-emerald-400">{t("rfq_detail.invitations_section.copied_badge")}</span>
                                    </>
                                  ) : (
                                    <>
                                      <Copy size={12} />
                                      <span>{t("rfq_detail.copy_link_btn")}</span>
                                    </>
                                  )}
                                </button>
                              )}
                              {!inv.is_revoked && rfq.status !== "cancelled" && (
                                <button
                                  onClick={() => handleRevokeInvitation(inv.id)}
                                  disabled={revokingInvitationId === inv.id}
                                  className="px-2 py-1 rounded text-[11px] font-medium bg-amber-500/10 hover:bg-amber-500/20 text-amber-500 border border-amber-500/30 transition-colors"
                                  title={t("rfq_detail.invitations_section.tooltip_revoke_invite")}
                                >
                                  {revokingInvitationId === inv.id ? (
                                    <Loader2 size={12} className="animate-spin inline" />
                                  ) : (
                                    t("rfq_detail.invitations_section.btn_revoke")
                                  )}
                                </button>
                              )}
                              {isFailed && (
                                <button
                                  onClick={() => handleRetryInvitation(inv.id)}
                                  disabled={retryingInvitationId === inv.id}
                                  className="px-2 py-1 rounded text-[11px] font-medium bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 transition-colors"
                                >
                                  {retryingInvitationId === inv.id ? (
                                    <Loader2 size={12} className="animate-spin inline mr-1" />
                                  ) : (
                                    <RefreshCw size={12} className="inline mr-1" />
                                  )}
                                  Tekrar Dene
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

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

      {/* ── Phase 9: Invite Supplier Modal ───────────────────────── */}
      {isInviteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-hover border border-border rounded-lg shadow-xl w-full max-w-md overflow-hidden flex flex-col">
            <div className="p-6 border-b border-border flex justify-between items-center bg-surface">
              <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
                <Mail size={18} className="text-blue-500" />
                {t("rfq_detail.invitations_section.invite_modal_title")}
              </h3>
              <button
                onClick={() => { setIsInviteModalOpen(false); setInviteError(null); }}
                className="text-text-muted hover:text-text-primary transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSendInvitation} className="p-6 flex flex-col gap-4">
              {inviteError && (
                <div className="p-3 rounded bg-danger/10 border border-danger/20 text-danger text-xs font-medium">
                  {inviteError}
                </div>
              )}

              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-text-secondary">{t("rfq_detail.invitations_section.invite_select_supplier_label")}</label>
                <select
                  value={inviteSupplierId}
                  onChange={(e) => {
                    const suppId = e.target.value;
                    setInviteSupplierId(suppId);
                    const selected = suppliers.find(s => s.id === suppId);
                    if (selected) {
                      if (selected.email) setInviteEmail(selected.email);
                      if (selected.name) setInviteName(selected.name);
                    }
                  }}
                  className="px-2.5 py-1.5 text-xs bg-background border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                >
                  <option value="">{t("rfq_detail.invitations_section.invite_select_supplier_default")}</option>
                  {suppliers.map(s => (
                    <option key={s.id} value={s.id}>
                      {s.name} {s.email ? `(${s.email})` : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-text-secondary">{t("rfq_detail.invitations_section.invite_recipient_email_label")}</label>
                <input
                  type="email"
                  required
                  placeholder="tedarikci@firma.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="px-2.5 py-1.5 text-xs bg-background border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-text-secondary">{t("rfq_detail.invitations_section.invite_contact_name_label")}</label>
                <input
                  type="text"
                  placeholder={t("rfq_detail.invitations_section.invite_contact_name_placeholder")}
                  value={inviteName}
                  onChange={(e) => setInviteName(e.target.value)}
                  className="px-2.5 py-1.5 text-xs bg-background border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-text-secondary">{t("rfq_detail.invitations_section.invite_message_label")}</label>
                <textarea
                  rows={3}
                  placeholder={t("rfq_detail.invitations_section.invite_message_placeholder")}
                  value={inviteCustomMessage}
                  onChange={(e) => setInviteCustomMessage(e.target.value)}
                  className="px-2.5 py-1.5 text-xs bg-background border border-border rounded text-text-primary focus:outline-none focus:border-primary resize-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <button
                  type="button"
                  onClick={() => { setIsInviteModalOpen(false); setInviteError(null); }}
                  className="px-3.5 py-2 text-xs font-medium text-text-muted hover:text-text-primary"
                >{t("quotes_page.cancel_btn")}</button>
                <button
                  type="submit"
                  disabled={isSendingInvite || !inviteEmail.trim()}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded transition-colors"
                >
                  {isSendingInvite ? (
                    <>
                      <Loader2 size={13} className="animate-spin" />
                      <span>{t("rfq_detail.invitations_section.invite_queueing")}</span>
                    </>
                  ) : (
                    <>
                      <Mail size={13} />
                      <span>{t("rfq_detail.invitations_section.invite_send_btn")}</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Upload Quote Modal */}
      {isUploadQuoteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-hover border border-border rounded-lg shadow-xl w-full max-w-md overflow-hidden flex flex-col">
            <div className="p-6 border-b border-border flex justify-between items-center bg-surface">
              <h3 className="text-lg font-semibold text-text-primary">{t("rfq_detail.actions.upload_quote")}</h3>
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
                    <span className="text-xs font-semibold text-text-primary uppercase">{t("rfq_detail.new_supplier_details")}</span>
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
                      <label className="text-xs font-medium text-text-secondary">{t("rfq_detail.email_label")}</label>
                      <input 
                        type="email"
                        placeholder="contact@acme.com"
                        value={newSupplierEmail}
                        onChange={(e) => setNewSupplierEmail(e.target.value)}
                        className="px-2.5 py-1.5 text-xs bg-background border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-text-secondary">{t("rfq_detail.phone_label")}</label>
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
                <label className="text-sm font-medium text-text-secondary">Quote Document (PDF, Excel, Image) *</label>
                <div className="border-2 border-dashed border-border rounded-lg p-6 flex flex-col items-center justify-center text-center group hover:border-primary/50 transition-colors relative">
                  <input 
                    type="file" 
                    accept=".pdf,.xlsx,.png,.jpg,.jpeg"
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
                      <p className="text-xs text-text-muted mt-1">{t("rfq_detail.ready_to_upload")}</p>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm font-medium text-text-primary">{t("rfq_detail.drag_drop_upload")}</p>
                      <p className="text-xs text-text-muted mt-1">PDF, Excel (.xlsx), PNG, JPG up to 50MB</p>
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
                <h3 className="text-base font-semibold text-text-primary">{t("quotes_page.delete_rfq_title")}</h3>
              </div>
              <p className="text-sm text-text-muted">
                {t("rfq_detail.modals.delete_rfq_warning")}
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
              >{t("quotes_page.cancel_btn")}</button>
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
                <h3 className="text-base font-semibold text-text-primary">{t("quotes_page.delete_quote_title")}</h3>
              </div>
              <p className="text-sm text-text-muted">
                {t("rfq_detail.modals.delete_quote_warning")}
              </p>
              <div className="mt-4 p-3 rounded-lg bg-bg border border-border text-xs">
                <p className="font-semibold text-text-primary">{quoteToDelete.supplier_name || t("quotes_page.table_supplier")}</p>
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
              >{t("quotes_page.cancel_btn")}</button>
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
                  <h3 className="text-base font-semibold text-text-primary">{t("rfq_detail.modals.cancel_rfq_title")}</h3>
                  <p className="text-xs text-text-muted mt-0.5">{t("rfq_detail.modals.cancel_rfq_desc")}</p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    {t("rfq_detail.modals.cancel_rfq_reason_label")}
                  </label>
                  <textarea
                    rows={3}
                    placeholder={t("rfq_detail.modals.cancel_rfq_reason_placeholder")}
                    value={rfqCancelReason}
                    onChange={(e) => setRfqCancelReason(e.target.value)}
                    className="w-full text-xs p-3 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-amber-500 transition-colors"
                  />
                  <p className="text-[11px] text-text-muted mt-1">{t("rfq_detail.modals.cancel_rfq_reason_help")}</p>
                </div>

                {purchaseOrders.some(p => p.status !== 'cancelled') && (
                  <label className="flex items-start gap-2.5 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={rfqCancelPos}
                      onChange={(e) => setRfqCancelPos(e.target.checked)}
                      className="mt-0.5 rounded border-amber-500 text-amber-500 focus:ring-0"
                    />
                    <span>{t("rfq_detail.modals.cancel_rfq_auto_po")}</span>
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
              >{t("quotes_page.cancel_btn")}</button>
              <button
                onClick={handleCancelRfq}
                disabled={isCancellingRfq || !rfqCancelReason.trim() || rfqCancelReason.trim().length < 3}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isCancellingRfq && <Loader2 size={13} className="animate-spin" />}
                {isCancellingRfq ? t("rfq_detail.modals.cancelling_rfq") : t("rfq_detail.modals.btn_confirm_cancel_rfq")}
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
                  <h3 className="text-base font-semibold text-text-primary">{t("rfq_detail.modals.cancel_po_title")}</h3>
                  <p className="text-xs text-text-muted font-mono mt-0.5">{poToCancel.po_number}</p>
                </div>
              </div>

              <div className="space-y-4">
                <p className="text-xs text-text-muted">
                  {t("rfq_detail.modals.cancel_po_desc")}
                </p>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    {t("rfq_detail.modals.cancel_po_reason_label")}
                  </label>
                  <textarea
                    rows={3}
                    placeholder={t("rfq_detail.modals.cancel_po_reason_placeholder")}
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
              >{t("quotes_page.cancel_btn")}</button>
              <button
                onClick={handleCancelPo}
                disabled={isCancellingPo || !poCancelReason.trim() || poCancelReason.trim().length < 3}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isCancellingPo && <Loader2 size={13} className="animate-spin" />}
                {isCancellingPo ? t("rfq_detail.modals.cancelling_po") : t("rfq_detail.modals.btn_confirm_cancel_po")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Deliver PO ── */}
      {poToDeliver && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <div className="flex items-center gap-3 text-amber-500 mb-4">
                <div className="p-2.5 rounded-full bg-amber-500/10 border border-amber-500/20">
                  <Truck size={22} />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-text-primary">{t("rfq_detail.modals.deliver_po_title")}</h3>
                  <p className="text-xs text-text-muted font-mono mt-0.5">{poToDeliver.po_number}</p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    Fiilî Teslim Tarihi
                  </label>
                  <input
                    type="date"
                    value={deliverDate}
                    onChange={(e) => setDeliverDate(e.target.value)}
                    className="w-full text-xs p-2.5 rounded-lg bg-bg border border-border text-text-primary focus:outline-none focus:border-amber-500 transition-colors"
                  />
                  <p className="text-[11px] text-text-muted mt-1">{t("rfq_detail.modals.deliver_po_date_help")}</p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    {t("rfq_detail.modals.deliver_po_notes_label")}
                  </label>
                  <textarea
                    rows={3}
                    placeholder={t("rfq_detail.modals.deliver_po_notes_placeholder")}
                    value={deliverNotes}
                    onChange={(e) => setDeliverNotes(e.target.value)}
                    className="w-full text-xs p-3 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-amber-500 transition-colors"
                  />
                </div>

                {deliverPoError && (
                  <div className="p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                    {deliverPoError}
                  </div>
                )}
              </div>
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button
                onClick={() => { setPoToDeliver(null); setDeliverPoError(null); }}
                disabled={isDeliveringPo}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >{t("quotes_page.cancel_btn")}</button>
              <button
                onClick={handleDeliverPo}
                disabled={isDeliveringPo}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isDeliveringPo && <Loader2 size={13} className="animate-spin" />}
                {isDeliveringPo ? t("rfq_detail.modals.delivering_po") : t("rfq_detail.modals.btn_confirm_deliver_po")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Complete PO ── */}
      {poToComplete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <div className="flex items-center gap-3 text-emerald-400 mb-4">
                <div className="p-2.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
                  <PackageCheck size={22} />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-text-primary">{t("rfq_detail.modals.complete_po_title")}</h3>
                  <p className="text-xs text-text-muted font-mono mt-0.5">{poToComplete.po_number}</p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    {t("rfq_detail.modals.complete_po_amount_label")}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder={t("rfq_detail.modals.complete_po_amount_placeholder")}
                    value={finalAmount}
                    onChange={(e) => setFinalAmount(e.target.value)}
                    className="w-full text-xs p-2.5 rounded-lg bg-bg border border-border text-text-primary focus:outline-none focus:border-emerald-500 transition-colors"
                  />
                  <p className="text-[11px] text-text-muted mt-1">{t("rfq_detail.modals.complete_po_amount_help")}</p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    {t("rfq_detail.modals.complete_po_notes_label")}
                  </label>
                  <textarea
                    rows={3}
                    placeholder={t("rfq_detail.modals.complete_po_notes_placeholder")}
                    value={completionNotes}
                    onChange={(e) => setCompletionNotes(e.target.value)}
                    className="w-full text-xs p-3 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-emerald-500 transition-colors"
                  />
                </div>

                {completePoError && (
                  <div className="p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                    {completePoError}
                  </div>
                )}
              </div>
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button
                onClick={() => { setPoToComplete(null); setCompletePoError(null); }}
                disabled={isCompletingPo}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >{t("quotes_page.cancel_btn")}</button>
              <button
                onClick={handleCompletePo}
                disabled={isCompletingPo}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isCompletingPo && <Loader2 size={13} className="animate-spin" />}
                {isCompletingPo ? t("rfq_detail.modals.completing_po") : t("rfq_detail.modals.btn_confirm_complete_po")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Add Quality Issue ── */}
      {poForQuality && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-surface border border-border rounded-xl shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <div className="flex items-center gap-3 text-amber-500 mb-4">
                <div className="p-2.5 rounded-full bg-amber-500/10 border border-amber-500/20">
                  <AlertCircle size={22} />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-text-primary">{t("rfq_detail.modals.quality_modal_title")}</h3>
                  <p className="text-xs text-text-muted font-mono mt-0.5">{poForQuality.po_number}</p>
                </div>
              </div>

              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-text-secondary mb-1.5">
                      {t("rfq_detail.modals.quality_issue_type_label")}
                    </label>
                    <select
                      value={qualityIssueType}
                      onChange={(e) => setQualityIssueType(e.target.value)}
                      className="w-full text-xs p-2.5 rounded-lg bg-bg border border-border text-text-primary focus:outline-none focus:border-amber-500 transition-colors"
                    >
                      <option value="defect">{t("rfq_detail.modals.quality_type_defect")}</option>
                      <option value="late_delivery">{t("rfq_detail.late_delivery_option")}</option>
                      <option value="missing_items">{t("rfq_detail.modals.quality_type_missing")}</option>
                      <option value="damaged">{t("rfq_detail.modals.quality_type_damaged")}</option>
                      <option value="documentation">{t("rfq_detail.modals.quality_type_docs")}</option>
                      <option value="other">{t("rfq_detail.modals.quality_type_other")}</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-text-secondary mb-1.5">
                      {t("rfq_detail.modals.quality_severity_label")}
                    </label>
                    <select
                      value={qualitySeverity}
                      onChange={(e) => setQualitySeverity(e.target.value)}
                      className="w-full text-xs p-2.5 rounded-lg bg-bg border border-border text-text-primary focus:outline-none focus:border-amber-500 transition-colors"
                    >
                      <option value="low">{t("rfq_detail.modals.quality_sev_low")}</option>
                      <option value="medium">{t("rfq_detail.modals.quality_sev_medium")}</option>
                      <option value="critical">{t("rfq_detail.modals.quality_sev_critical")}</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    {t("rfq_detail.modals.quality_count_label")}
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={qualityRejectionCount}
                    onChange={(e) => setQualityRejectionCount(Math.max(0, parseInt(e.target.value) || 0))}
                    className="w-full text-xs p-2.5 rounded-lg bg-bg border border-border text-text-primary focus:outline-none focus:border-amber-500 transition-colors"
                  />
                  <p className="text-[11px] text-text-muted mt-1">{t("rfq_detail.modals.quality_count_help")}</p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">
                    {t("rfq_detail.modals.quality_desc_label")}
                  </label>
                  <textarea
                    rows={3}
                    placeholder={t("rfq_detail.modals.quality_desc_placeholder")}
                    value={qualityDescription}
                    onChange={(e) => setQualityDescription(e.target.value)}
                    className="w-full text-xs p-3 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-muted focus:outline-none focus:border-amber-500 transition-colors"
                  />
                  <p className="text-[11px] text-text-muted mt-1">{t("rfq_detail.modals.quality_desc_help")}</p>
                </div>

                {qualityError && (
                  <div className="p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-xs text-red-300">
                    {qualityError}
                  </div>
                )}
              </div>
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface-elevated/40 flex justify-end gap-3">
              <button
                onClick={() => { setPoForQuality(null); setQualityError(null); }}
                disabled={isSavingQuality}
                className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >{t("quotes_page.cancel_btn")}</button>
              <button
                onClick={handleSaveQualityIssue}
                disabled={isSavingQuality || !qualityDescription.trim() || qualityDescription.trim().length < 3}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white transition-colors shadow-sm disabled:opacity-50"
              >
                {isSavingQuality && <Loader2 size={13} className="animate-spin" />}
                {isSavingQuality ? t("rfq_detail.modals.saving_quality") : t("rfq_detail.modals.btn_save_quality")}
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
