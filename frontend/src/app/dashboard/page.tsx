"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { 
  ArrowUpRight, 
  ArrowDownRight, 
  FileText, 
  Clock, 
  ShieldAlert, 
  Search, 
  Filter, 
  X, 
  UploadCloud, 
  ChevronLeft, 
  ChevronRight, 
  FilterX, 
  Loader2, 
  FileIcon, 
  Plus, 
  Trash2 
} from "lucide-react";
import { rfqsApi } from "@/lib/api/rfqs";
import { DashboardRFQResponse, SupplierResponse } from "@/lib/api/types";
import { useTranslation } from "@/lib/i18n/I18nContext";
import { formatCurrency, formatDate } from "@/lib/i18n/formatters";

export default function DashboardPage() {
  const router = useRouter();
  const { t, locale } = useTranslation();
  const [rfqs, setRfqs] = useState<DashboardRFQResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  
  // Modal states
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDescription, setUploadDescription] = useState("");
  const [uploadBudget, setUploadBudget] = useState("");
  const [uploadMaxDeliveryDays, setUploadMaxDeliveryDays] = useState("");
  const [uploadMinWarrantyMonths, setUploadMinWarrantyMonths] = useState("");
  const [uploadPaymentTerms, setUploadPaymentTerms] = useState("net-30");
  const [uploadItems, setUploadItems] = useState<{ description: string; quantity: string; unit: string }[]>([
    { description: "", quantity: "1", unit: "Adet" }
  ]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setIsLoading(true);
        const data = await rfqsApi.getRecentRfqs();
        setRfqs(data);
        setError(null);
      } catch (err: any) {
        setError(err.message || "Failed to load dashboard data.");
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, []);

  const handleCreateSubmit = async () => {
    if (!uploadTitle.trim()) {
      setUploadError(t("dashboard_home.create_modal.title_required_error"));
      return;
    }
    
    try {
      setIsUploading(true);
      setUploadError(null);
      
      const validItems = uploadItems
        .filter(it => it.description.trim())
        .map(it => ({
          description: it.description.trim(),
          quantity: parseFloat(it.quantity) || 1,
          unit: it.unit.trim() || null
        }));

      const rfq = await rfqsApi.createRfq({
        title: uploadTitle.trim(),
        description: uploadDescription.trim() || undefined,
        budget: uploadBudget ? parseFloat(uploadBudget) : undefined,
        max_delivery_days: uploadMaxDeliveryDays ? parseInt(uploadMaxDeliveryDays) : undefined,
        min_warranty_months: uploadMinWarrantyMonths ? parseInt(uploadMinWarrantyMonths) : undefined,
        payment_terms: uploadPaymentTerms.trim() || undefined,
        items: validItems.length > 0 ? validItems : undefined
      });
      
      router.push(`/dashboard/rfq/${rfq.id}`);
      
    } catch (err: any) {
      setUploadError(err.message || "An error occurred during creation.");
      setIsUploading(false);
    }
  };

  const filteredRFQs = rfqs.filter(rfq => {
    const searchLower = searchQuery.toLowerCase();
    const titleMatch = rfq.title ? rfq.title.toLowerCase().includes(searchLower) : false;
    const idMatch = rfq.id.toLowerCase().includes(searchLower);
    const supplierMatch = rfq.recommended_supplier_name ? rfq.recommended_supplier_name.toLowerCase().includes(searchLower) : false;
    
    const matchesSearch = titleMatch || idMatch || supplierMatch;
    const matchesStatus = statusFilter ? rfq.status === statusFilter : true;
    return matchesSearch && matchesStatus;
  });

  const getStatusBadge = (status: string) => {
    switch(status) {
      case 'approved': return { bg: 'bg-success/10', text: 'text-success', border: 'border-success/20', dot: 'bg-success' };
      case 'rejected': return { bg: 'bg-danger/10', text: 'text-danger', border: 'border-danger/20', dot: 'bg-danger' };
      case 'pending_approval': return { bg: 'bg-warning/10', text: 'text-warning', border: 'border-warning/20', dot: 'bg-warning' };
      case 'draft': return { bg: 'bg-surface-hover', text: 'text-text-secondary', border: 'border-border', dot: 'bg-text-muted' };
      default: return { bg: 'bg-surface-hover', text: 'text-text-secondary', border: 'border-border', dot: 'bg-text-muted' };
    }
  };

  const getStatusLabel = (status: string) => {
    switch(status) {
      case 'approved': return t("common.status.approved");
      case 'rejected': return t("common.status.rejected");
      case 'pending_approval': return t("common.status.pending");
      case 'draft': return t("common.status.draft");
      default: return status;
    }
  };

  return (
    <div className="flex flex-col gap-8">
      
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
            {t("dashboard_home.title")}
          </h1>
          <p className="text-sm text-text-muted mt-1">
            {t("dashboard_home.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setIsUploadOpen(true)}
            className="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm"
          >
            {t("dashboard_home.new_rfq")}
          </button>
        </div>
      </div>

      <div className="bg-surface-elevated border border-border rounded-xl shadow-sm overflow-hidden flex flex-col">
        <div className="p-4 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-surface/50">
          <div className="relative max-w-md w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" size={18} />
            <input 
              type="text" 
              placeholder={t("dashboard_home.search_placeholder")} 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 text-sm bg-surface border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          <div className="flex items-center gap-2">
            <select 
              value={statusFilter || ""}
              onChange={(e) => setStatusFilter(e.target.value || null)}
              className="px-3 py-2 text-sm bg-surface dark:bg-slate-800 border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option className="bg-surface text-text-primary dark:bg-slate-800 dark:text-slate-100" value="">{t("dashboard_home.all_statuses")}</option>
              <option className="bg-surface text-text-primary dark:bg-slate-800 dark:text-slate-100" value="draft">{t("common.status.draft")}</option>
              <option className="bg-surface text-text-primary dark:bg-slate-800 dark:text-slate-100" value="pending_approval">{t("common.status.pending")}</option>
              <option className="bg-surface text-text-primary dark:bg-slate-800 dark:text-slate-100" value="approved">{t("common.status.approved")}</option>
              <option className="bg-surface text-text-primary dark:bg-slate-800 dark:text-slate-100" value="rejected">{t("common.status.rejected")}</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto min-h-[300px]">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-full py-12 text-text-muted">
              <Loader2 className="animate-spin mb-4" size={32} />
              <p>{t("dashboard_home.loading_rfqs")}</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full py-12 text-danger">
              <ShieldAlert size={32} className="mb-4" />
              <p>{error}</p>
              <button onClick={() => window.location.reload()} className="mt-4 px-4 py-2 bg-surface border border-border rounded hover:bg-surface-hover text-text-primary text-sm">
                {t("dashboard_home.retry")}
              </button>
            </div>
          ) : filteredRFQs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full py-12 text-text-muted">
              <FileText size={32} className="mb-4 opacity-50" />
              <p>{t("dashboard_home.no_rfqs_found")}</p>
            </div>
          ) : (
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-text-muted uppercase bg-surface/50 border-b border-border">
                <tr>
                  <th className="px-6 py-4 font-medium">{t("dashboard_home.table.rfq_id")}</th>
                  <th className="px-6 py-4 font-medium">{t("dashboard_home.table.created")}</th>
                  <th className="px-6 py-4 font-medium">{t("dashboard_home.table.title_supplier")}</th>
                  <th className="px-6 py-4 font-medium">{t("dashboard_home.table.recommended_tco")}</th>
                  <th className="px-6 py-4 font-medium">{t("dashboard_home.table.status")}</th>
                  <th className="px-6 py-4 font-medium text-right">{t("dashboard_home.table.action")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredRFQs.map((rfq) => {
                  const statusBadge = getStatusBadge(rfq.status);
                  
                  return (
                    <tr key={rfq.id} className="hover:bg-surface-hover/50 transition-colors group">
                      <td className="px-6 py-4 font-medium text-text-primary">
                        {rfq.id.split('-')[0]}...
                      </td>
                      <td className="px-6 py-4 text-text-secondary whitespace-nowrap">
                        {formatDate(rfq.created_at, locale)}
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-medium text-text-primary">
                          {rfq.title || t("dashboard_home.table.untitled")}
                        </div>
                        <div className="text-text-muted text-xs mt-0.5">
                          {rfq.recommended_supplier_name || t("dashboard_home.table.no_quotes")}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-medium text-text-primary">
                          {formatCurrency(rfq.recommended_tco, "TRY", locale)}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center gap-1.5 ${statusBadge.bg} ${statusBadge.text} px-2.5 py-1 rounded-full text-[11px] font-medium border ${statusBadge.border}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${statusBadge.dot}`}></span>
                          {getStatusLabel(rfq.status)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Link 
                          href={`/dashboard/rfq/${rfq.id}`}
                          className="inline-flex items-center justify-center text-primary font-medium hover:text-primary-hover transition-colors text-xs"
                        >
                          {t("dashboard_home.table.view_details")}
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── New RFQ Modal ──────────────────────────────────────────────── */}
      {isUploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-surface-elevated border border-border rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-surface/50">
              <div>
                <h2 className="font-semibold text-text-primary text-lg">
                  {t("dashboard_home.create_modal.title")}
                </h2>
                <p className="text-xs text-text-muted mt-0.5">
                  {t("dashboard_home.create_modal.subtitle")}
                </p>
              </div>
              <button onClick={() => { setIsUploadOpen(false); setUploadError(null); }} className="text-text-muted hover:text-text-primary transition-colors">
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 flex flex-col gap-6 overflow-y-auto flex-1">
              {uploadError && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-500 text-xs rounded-md font-medium">
                  {uploadError}
                </div>
              )}

              {/* Basic Info */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="sm:col-span-2 flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-text-primary">
                    {t("dashboard_home.create_modal.title_label")} <span className="text-red-500">*</span>
                  </label>
                  <input 
                    type="text" 
                    value={uploadTitle}
                    onChange={(e) => setUploadTitle(e.target.value)}
                    placeholder={t("dashboard_home.create_modal.title_placeholder")} 
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div className="sm:col-span-2 flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-text-primary">
                    {t("dashboard_home.create_modal.desc_label")}
                  </label>
                  <textarea 
                    rows={2}
                    value={uploadDescription}
                    onChange={(e) => setUploadDescription(e.target.value)}
                    placeholder={t("dashboard_home.create_modal.desc_placeholder")} 
                    className="px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary transition-colors resize-none"
                  />
                </div>
              </div>

              {/* Line Items */}
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-text-primary uppercase tracking-wider">
                    {t("dashboard_home.create_modal.items_header", { count: uploadItems.length })}
                  </label>
                  <button 
                    type="button"
                    onClick={() => setUploadItems([...uploadItems, { description: "", quantity: "1", unit: "Adet" }])}
                    className="flex items-center gap-1 text-xs text-primary hover:text-primary-hover font-medium transition-colors"
                  >
                    <Plus size={14} /> {t("dashboard_home.create_modal.add_item")}
                  </button>
                </div>

                <div className="flex flex-col gap-2.5">
                  {uploadItems.map((item, idx) => (
                    <div key={idx} className="flex items-center gap-2 bg-surface/50 p-2.5 rounded-lg border border-border">
                      <div className="flex-1">
                        <input 
                          type="text"
                          placeholder={t("dashboard_home.create_modal.item_desc_placeholder")}
                          value={item.description}
                          onChange={(e) => {
                            const updated = [...uploadItems];
                            updated[idx].description = e.target.value;
                            setUploadItems(updated);
                          }}
                          className="w-full px-2.5 py-1.5 text-xs bg-bg border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                        />
                      </div>
                      <div className="w-20">
                        <input 
                          type="number"
                          min="1"
                          placeholder={t("dashboard_home.create_modal.qty_placeholder")}
                          value={item.quantity}
                          onChange={(e) => {
                            const updated = [...uploadItems];
                            updated[idx].quantity = e.target.value;
                            setUploadItems(updated);
                          }}
                          className="w-full px-2.5 py-1.5 text-xs bg-bg border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                        />
                      </div>
                      <div className="w-20">
                        <input 
                          type="text"
                          placeholder={t("dashboard_home.create_modal.unit_placeholder")}
                          value={item.unit}
                          onChange={(e) => {
                            const updated = [...uploadItems];
                            updated[idx].unit = e.target.value;
                            setUploadItems(updated);
                          }}
                          className="w-full px-2.5 py-1.5 text-xs bg-bg border border-border rounded text-text-primary focus:outline-none focus:border-primary"
                        />
                      </div>
                      {uploadItems.length > 1 && (
                        <button 
                          type="button"
                          onClick={() => setUploadItems(uploadItems.filter((_, i) => i !== idx))}
                          className="p-1 text-text-muted hover:text-red-500 transition-colors"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Conditions / Budget */}
              <div className="flex flex-col gap-3 pt-2 border-t border-border">
                <label className="text-xs font-semibold text-text-primary uppercase tracking-wider">
                  {t("dashboard_home.create_modal.commercial_conditions")}
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs text-text-secondary">
                      {t("dashboard_home.create_modal.target_budget")}
                    </label>
                    <input 
                      type="number"
                      placeholder={t("dashboard_home.create_modal.budget_placeholder")}
                      value={uploadBudget}
                      onChange={(e) => setUploadBudget(e.target.value)}
                      className="px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs text-text-secondary">
                      {t("dashboard_home.create_modal.max_delivery_days")}
                    </label>
                    <input 
                      type="number"
                      placeholder={t("dashboard_home.create_modal.days_placeholder")}
                      value={uploadMaxDeliveryDays}
                      onChange={(e) => setUploadMaxDeliveryDays(e.target.value)}
                      className="px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs text-text-secondary">
                      {t("dashboard_home.create_modal.min_warranty")}
                    </label>
                    <input 
                      type="number"
                      placeholder={t("dashboard_home.create_modal.warranty_placeholder")}
                      value={uploadMinWarrantyMonths}
                      onChange={(e) => setUploadMinWarrantyMonths(e.target.value)}
                      className="px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs text-text-secondary">
                      {t("dashboard_home.create_modal.payment_terms")}
                    </label>
                    <input 
                      type="text"
                      placeholder={t("dashboard_home.create_modal.payment_placeholder")}
                      value={uploadPaymentTerms}
                      onChange={(e) => setUploadPaymentTerms(e.target.value)}
                      className="px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface/50 flex justify-end gap-3">
              <button 
                onClick={() => { setIsUploadOpen(false); setUploadError(null); }}
                disabled={isUploading}
                className="px-4 py-2 text-sm font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                {t("common.actions.cancel")}
              </button>
              <button 
                onClick={handleCreateSubmit}
                disabled={isUploading || !uploadTitle}
                className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-5 py-2 rounded text-sm font-medium transition-colors shadow-sm disabled:opacity-70"
              >
                {isUploading && <Loader2 size={14} className="animate-spin" />}
                {isUploading ? t("dashboard_home.create_modal.creating") : t("dashboard_home.create_modal.create_btn")}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
