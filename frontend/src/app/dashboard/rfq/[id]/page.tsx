"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
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
  Plus
} from "lucide-react";
import { rfqsApi } from "@/lib/api/rfqs";
import { RFQ, Quote, AnalysisResponse, TCOResultResponse, ComplianceCheckResponse, EvidenceItemResponse } from "@/lib/api/types";

export default function RFQDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const resolvedParams = React.use(params);
  const rfqId = resolvedParams.id;
  
  const [rfq, setRfq] = useState<RFQ | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [selectedQuoteId, setSelectedQuoteId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [purchaseOrders, setPurchaseOrders] = useState<any[]>([]);
  
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Workflow states
  const [isApproving, setIsApproving] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);

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
    } catch (err: any) {
      setUploadError(err.message || "Dosya yüklenirken bir hata oluştu.");
    } finally {
      setIsUploading(false);
    }
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

  const handleApprove = async () => {
    if (!analysis) return;
    try {
      setIsApproving(true);
      setApprovalError(null);
      
      await rfqsApi.reviewAnalysis(analysis.id, {
        status: "approved",
        comment: "Approved via UI",
        selected_quote_id: displayQuote?.id,
        acknowledged_policy_violation: warningsCount > 0
      });
      
      // Refresh page data after approval
      window.location.reload();
      
    } catch (err: any) {
      setApprovalError(err.message || "Approval failed.");
    } finally {
      setIsApproving(false);
    }
  };

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
        <Link href="/dashboard" className="text-sm text-primary hover:underline mt-4">Return to Dashboard</Link>
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
          <Link 
            href="/dashboard"
            className="w-8 h-8 rounded-full border border-border flex items-center justify-center text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors"
          >
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-text-primary">{rfq.title || rfq.id.split('-')[0]}</h1>
              <span className={`inline-flex items-center gap-1.5 ${statusBadge.bg} ${statusBadge.text} px-2.5 py-1 rounded-full text-[11px] font-medium border ${statusBadge.border}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${statusBadge.dot}`}></span>
                {formattedStatus}
              </span>
            </div>
            <p className="text-sm text-text-muted mt-1">Uploaded on {new Date(rfq.created_at).toLocaleDateString()}</p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setIsUploadQuoteOpen(true)}
            className="flex items-center gap-2 bg-surface-elevated border border-border hover:bg-bg text-primary px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm"
          >
            <Plus size={16} />
            Add Supplier Quote
          </button>
          
          {displayQuote?.quote_document_id && (
            <button className="flex items-center gap-2 bg-surface-elevated border border-border hover:bg-bg text-text-primary px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm">
              <Download size={16} />
              Original Document
            </button>
          )}
          {rfq.status === 'pending_approval' && purchaseOrders.length === 0 && (
            <button 
              onClick={() => setIsConfirmOpen(true)}
              className="flex items-center gap-2 bg-success hover:bg-success/90 text-white px-6 py-2 rounded text-sm font-medium transition-colors shadow-sm"
            >
              <Check size={16} />
              Approve & Create PO
            </button>
          )}
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

        
        {/* ── Left Column: Extraction & Calculation ────────────────────────── */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          
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
                  {(displayQuote.discount_amount || 0) > 0 && (
                    <div className="flex justify-between w-64 text-text-muted">
                      <span>Discount:</span>
                      <span className="text-success">- ₺ {displayQuote.discount_amount.toLocaleString('en-US')}</span>
                    </div>
                  )}
                  <div className="flex justify-between w-64 text-text-muted border-b border-border pb-2">
                    <span>VAT ({(displayQuote.vat_rate || 0) * 100}%):</span>
                    <span>₺ {displayQuote.vat_amount?.toLocaleString('en-US') || 0}</span>
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

        {/* ── Right Column: AI & Policy Guardrails ──────────────────────── */}
        <div className="flex flex-col gap-6">
          
          <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4 flex items-center gap-2">
              <ShieldCheck size={16} className="text-primary" />
              AI Decision Engine
            </h2>

            {analysis ? (
              <>
                <div className="mb-6">
                  <div className="text-[10px] uppercase font-bold text-text-muted mb-2 tracking-wider">AI RECOMMENDATION</div>
                  <div className={`flex items-center gap-2 text-lg font-semibold ${analysis.recommendation?.verification_status === 'verified' ? 'text-success' : 'text-amber-500'}`}>
                    {analysis.recommendation?.verification_status ? analysis.recommendation.verification_status.toUpperCase() : 'PENDING'}
                  </div>
                  {warningsCount > 0 && (
                    <div className="text-xs text-amber-500 mt-1">Review {warningsCount} warning(s) before approval.</div>
                  )}
                </div>

                <div className="mb-6">
                  <div className="text-[10px] uppercase font-bold text-text-muted mb-2 tracking-wider">Reasoning & Checks</div>
                  <p className="text-xs text-text-muted mb-4 leading-relaxed">
                    {analysis.recommendation?.reasoning || 'No AI reasoning provided yet.'}
                  </p>
                  
                  <div className="space-y-3">
                    {analysis.compliance_checks?.map((check, idx) => (
                      <div key={idx} className="flex gap-2 items-start">
                        {check.result === 'pass' ? (
                          <CheckCircle size={14} className="text-success mt-0.5 shrink-0" />
                        ) : (
                          <AlertTriangle size={14} className="text-amber-500 mt-0.5 shrink-0" />
                        )}
                        <div className="text-xs text-text-primary">
                          <span className="font-medium">{check.rule_description}</span>: {check.notes} 
                          <span className="text-text-muted block mt-0.5">Value: {check.actual_value} (Required: {check.required_value})</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {analysis.evidence_items?.length > 0 && (
                  <div>
                    <div className="text-[10px] uppercase font-bold text-text-muted mb-2 tracking-wider">Evidence Links</div>
                    <div className="flex flex-wrap gap-2">
                      {analysis.evidence_items.map((evidence, idx) => (
                        <button key={idx} className="text-[10px] bg-bg border border-border px-2 py-1.5 rounded hover:bg-surface transition-colors text-text-primary flex items-center gap-1 font-medium" title={evidence.claim}>
                          <FileText size={10} className="text-primary" /> {evidence.source_reference}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="py-8 text-center text-text-muted text-sm border-2 border-dashed border-border rounded-lg">
                <AlertTriangle size={24} className="mx-auto mb-2 opacity-50" />
                <p>No analysis has been generated for this RFQ yet.</p>
              </div>
            )}
          </div>

          {purchaseOrders.length > 0 ? (
            <div className="bg-success border border-success/80 rounded-xl p-6 shadow-sm text-white">
              <h2 className="text-sm font-semibold uppercase tracking-wider mb-2 flex items-center gap-2">
                <CheckCircle size={16} className="text-white" />
                Action Completed: Purchase Order Issued
              </h2>
              <p className="text-xs text-success-foreground/80 mb-4 leading-relaxed text-slate-100">
                The RFQ was approved and the following Purchase Order was successfully generated.
              </p>
              {purchaseOrders.map(po => (
                <div key={po.id} className="bg-white/10 rounded p-3 text-xs font-mono text-white border border-white/20 mb-2">
                  PO Number: {po.po_number}<br/>
                  Status: {po.status.toUpperCase()}<br/>
                  Date: {new Date(po.created_at).toLocaleString()}<br/>
                  Email Notification: {po.email_sent ? "Sent" : "Pending"}
                </div>
              ))}
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

      {/* ── Approval Confirmation Modal ─────────────────────────────────── */}
      {isConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 backdrop-blur-sm p-4">
          <div className="bg-surface-elevated border border-border rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold text-text-primary">Approve this recommendation?</h2>
              <button onClick={() => setIsConfirmOpen(false)} className="text-text-muted hover:text-text-primary transition-colors">
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 flex flex-col gap-5">
              <div className="bg-bg border border-border rounded-lg p-4 text-sm">
                <div className="flex justify-between mb-2">
                  <span className="text-text-muted">Supplier:</span>
                  <span className="font-medium text-text-primary">{displayQuote?.supplier_name || 'Unknown'}</span>
                </div>
                <div className="flex justify-between mb-2">
                  <span className="text-text-muted">Total Value (TCO):</span>
                  <span className="font-medium text-text-primary">₺ {displayTCO?.total_tco.toLocaleString('en-US') || displayQuote?.total_price.toLocaleString('en-US')}</span>
                </div>
                <div className="flex justify-between mb-2">
                  <span className="text-text-muted">AI Recommendation:</span>
                  <span className="font-medium text-text-primary">{analysis?.recommendation?.verification_status || 'N/A'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Warnings:</span>
                  <span className={`font-medium ${warningsCount > 0 ? 'text-amber-500' : 'text-success'}`}>{warningsCount} ({warningsCount > 0 ? 'Review Required' : 'All Clear'})</span>
                </div>
              </div>

              <div>
                <div className="text-xs font-semibold text-text-primary mb-2">This action will:</div>
                <ul className="text-xs text-text-muted space-y-2">
                  <li className="flex items-center gap-2"><Check size={14} className="text-success" /> create a Purchase Order</li>
                  <li className="flex items-center gap-2"><Check size={14} className="text-success" /> trigger the configured notification workflow</li>
                  <li className="flex items-center gap-2"><Check size={14} className="text-success" /> record your approval in the audit log</li>
                </ul>
              </div>

              {approvalError && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-500 text-xs rounded-md font-medium">
                  {approvalError}
                </div>
              )}
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface/50 flex justify-end gap-3">
              <button 
                onClick={() => setIsConfirmOpen(false)}
                disabled={isApproving}
                className="px-4 py-2 text-sm font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button 
                onClick={handleApprove}
                disabled={isApproving}
                className="flex items-center gap-2 bg-success hover:bg-success/90 text-white px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm disabled:opacity-70"
              >
                {isApproving && <Loader2 size={14} className="animate-spin" />}
                {isApproving ? "Processing..." : "Approve & Create PO"}
              </button>
            </div>
          </div>
        </div>
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

    </div>
  );
}
