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
  FileIcon
} from "lucide-react";
import { rfqsApi } from "@/lib/api/rfqs";
import { DashboardRFQResponse, SupplierResponse } from "@/lib/api/types";

export default function DashboardPage() {
  const router = useRouter();
  const [rfqs, setRfqs] = useState<DashboardRFQResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  
  // Modal states
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadTitle, setUploadTitle] = useState("");
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
    if (!uploadTitle) {
      setUploadError("Please enter a title.");
      return;
    }
    
    try {
      setIsUploading(true);
      setUploadError(null);
      
      const rfq = await rfqsApi.createRfq({ title: uploadTitle });
      
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

  return (
    <div className="flex flex-col gap-8">
      
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">Dashboard</h1>
          <p className="text-sm text-text-muted mt-1">Overview of your procurement activities and AI analyses.</p>
        </div>
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setIsUploadOpen(true)}
            className="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm"
          >
            New RFQ
          </button>
        </div>
      </div>

      <div className="bg-surface-elevated border border-border rounded-xl shadow-sm overflow-hidden flex flex-col">
        <div className="p-4 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-surface/50">
          <div className="relative max-w-md w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" size={18} />
            <input 
              type="text" 
              placeholder="Search RFQs, suppliers..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 text-sm bg-background border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          <div className="flex items-center gap-2">
            <select 
              value={statusFilter || ""}
              onChange={(e) => setStatusFilter(e.target.value || null)}
              className="px-3 py-2 text-sm bg-background border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary transition-colors"
            >
              <option value="">All Statuses</option>
              <option value="draft">Draft</option>
              <option value="pending_approval">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto min-h-[300px]">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-full py-12 text-text-muted">
              <Loader2 className="animate-spin mb-4" size={32} />
              <p>Loading RFQs...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full py-12 text-danger">
              <ShieldAlert size={32} className="mb-4" />
              <p>{error}</p>
              <button onClick={() => window.location.reload()} className="mt-4 px-4 py-2 bg-surface border border-border rounded hover:bg-surface-hover text-text-primary text-sm">Retry</button>
            </div>
          ) : filteredRFQs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full py-12 text-text-muted">
              <FileText size={32} className="mb-4 opacity-50" />
              <p>No RFQs found.</p>
            </div>
          ) : (
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-text-muted uppercase bg-surface/50 border-b border-border">
                <tr>
                  <th className="px-6 py-4 font-medium">RFQ ID</th>
                  <th className="px-6 py-4 font-medium">Created</th>
                  <th className="px-6 py-4 font-medium">Title & Supplier</th>
                  <th className="px-6 py-4 font-medium">Recommended TCO</th>
                  <th className="px-6 py-4 font-medium">Status</th>
                  <th className="px-6 py-4 font-medium text-right">Action</th>
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
                        {new Date(rfq.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-medium text-text-primary">{rfq.title || "Untitled RFQ"}</div>
                        <div className="text-text-muted text-xs mt-0.5">{rfq.recommended_supplier_name || "No Quotes Yet"}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-medium text-text-primary">
                          {rfq.recommended_tco ? new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(rfq.recommended_tco) : "-"}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center gap-1.5 ${statusBadge.bg} ${statusBadge.text} px-2.5 py-1 rounded-full text-[11px] font-medium border ${statusBadge.border}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${statusBadge.dot}`}></span>
                          {rfq.status.replace('_', ' ').replace(/\w/g, l => l.toUpperCase())}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Link 
                          href={`/dashboard/rfq/${rfq.id}`}
                          className="inline-flex items-center justify-center text-primary font-medium hover:text-primary-hover transition-colors text-xs"
                        >
                          View Details
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

      {/* ?? New RFQ Modal ?? */}
      {isUploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-surface-elevated border border-border rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold text-text-primary">Create New RFQ</h2>
              <button onClick={() => { setIsUploadOpen(false); setUploadError(null); }} className="text-text-muted hover:text-text-primary transition-colors">
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 flex flex-col gap-6">
              <div className="flex flex-col gap-3">
                <label className="text-xs font-semibold text-text-primary">RFQ Title <span className="text-red-500">*</span></label>
                <input 
                  type="text" 
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  placeholder="e.g. Server Procurement 2026" 
                  className="px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary transition-colors"
                />
              </div>
              
              {uploadError && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-500 text-xs rounded-md font-medium">
                  {uploadError}
                </div>
              )}
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface/50 flex justify-end gap-3">
              <button 
                onClick={() => { setIsUploadOpen(false); setUploadError(null); }}
                disabled={isUploading}
                className="px-4 py-2 text-sm font-medium text-text-muted hover:text-text-primary transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button 
                onClick={handleCreateSubmit}
                disabled={isUploading || !uploadTitle}
                className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm disabled:opacity-70"
              >
                {isUploading && <Loader2 size={14} className="animate-spin" />}
                {isUploading ? "Creating..." : "Create RFQ"}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}