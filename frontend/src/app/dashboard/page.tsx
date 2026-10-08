"use client";

import { useState } from "react";
import Link from "next/link";
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
  FilterX
} from "lucide-react";

// Mock Data
const MOCK_RFQS = [
  { id: "RFQ-2026-089", createdAt: "Oct 08, 2026", supplier: "TechCorp Solutions", title: "IT Hardware Refresh", value: "407200", status: "Pending Review", aiStatus: "Recommended", badgeColor: "bg-amber-500", badgeBg: "bg-amber-500/10", textColor: "text-amber-500", aiColor: "text-primary" },
  { id: "RFQ-2026-088", createdAt: "Oct 06, 2026", supplier: "Global Systems Inc.", title: "ERP License Renewal", value: "840000", status: "Policy Violation", aiStatus: "Rejected", badgeColor: "bg-red-500", badgeBg: "bg-red-500/10", textColor: "text-red-500", aiColor: "text-red-500" },
  { id: "RFQ-2026-087", createdAt: "Oct 02, 2026", supplier: "Office Supplies Co.", title: "Q4 Stationeries", value: "12450", status: "Approved", aiStatus: "Approved by Manager", badgeColor: "bg-success", badgeBg: "bg-success/10", textColor: "text-success", aiColor: "text-text-muted" },
];

export default function DashboardPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  // Filter Logic
  const filteredRFQs = MOCK_RFQS.filter(rfq => {
    const matchesSearch = rfq.supplier.toLowerCase().includes(searchQuery.toLowerCase()) || rfq.id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter ? rfq.status === statusFilter : true;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="flex flex-col gap-8">
      
      {/* ── Header ──────────────────────────────────────────────────────── */}
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
            Upload Quote
          </button>
        </div>
      </div>

      {/* ── Metrics Grid ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-surface-elevated border border-border rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-medium text-text-muted">Total Processed Value</span>
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary">
              <span className="font-semibold text-xs">₺</span>
            </div>
          </div>
          <div className="text-2xl font-semibold text-text-primary mb-1">₺ 2.4M</div>
          <div className="flex items-center gap-1 text-xs text-success font-medium">
            <ArrowUpRight size={14} />
            <span>12% from last month</span>
          </div>
        </div>

        <div className="bg-surface-elevated border border-border rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-medium text-text-muted">Active RFQs</span>
            <div className="w-8 h-8 rounded-full bg-blue-500/10 flex items-center justify-center text-blue-500">
              <FileText size={16} />
            </div>
          </div>
          <div className="text-2xl font-semibold text-text-primary mb-1">14</div>
          <div className="flex items-center gap-1 text-xs text-text-muted font-medium">
            <span>4 awaiting review</span>
          </div>
        </div>

        <div className="bg-surface-elevated border border-border rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-medium text-text-muted">Pending Approval</span>
            <div className="w-8 h-8 rounded-full bg-amber-500/10 flex items-center justify-center text-amber-500">
              <Clock size={16} />
            </div>
          </div>
          <div className="text-2xl font-semibold text-text-primary mb-1">3</div>
          <div className="flex items-center gap-1 text-xs text-amber-500 font-medium">
            <span>Requires manager action</span>
          </div>
        </div>

        <div className="bg-surface-elevated border border-border rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-medium text-text-muted">Policy Exceptions</span>
            <div className="w-8 h-8 rounded-full bg-red-500/10 flex items-center justify-center text-red-500">
              <ShieldAlert size={16} />
            </div>
          </div>
          <div className="text-2xl font-semibold text-text-primary mb-1">2</div>
          <div className="flex items-center gap-1 text-xs text-red-500 font-medium">
            <ArrowDownRight size={14} />
            <span>Requires justification</span>
          </div>
        </div>
      </div>

      {/* ── Recent Quotes Table ────────────────────────────────────────── */}
      <div className="bg-surface-elevated border border-border rounded-xl shadow-sm overflow-hidden flex flex-col">
        
        {/* Table Header / Toolbar */}
        <div className="px-6 py-4 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-surface/50">
          <h2 className="font-semibold text-text-primary">Recent RFQs</h2>
          
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" size={14} />
              <input 
                type="text" 
                placeholder="Search suppliers..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-1.5 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary transition-colors w-full sm:w-64"
              />
            </div>
            
            {/* Filter Dropdown */}
            <div className="relative">
              <button 
                onClick={() => setIsFilterOpen(!isFilterOpen)}
                className={`flex items-center justify-center p-1.5 border rounded-md transition-colors ${statusFilter ? 'bg-primary/10 border-primary/30 text-primary' : 'border-border text-text-muted hover:bg-bg'}`}
              >
                <Filter size={16} />
              </button>
              
              {isFilterOpen && (
                <div className="absolute right-0 mt-2 w-48 bg-surface-elevated border border-border rounded-md shadow-lg z-50 py-1">
                  <div className="px-3 py-2 text-xs font-semibold text-text-muted uppercase border-b border-border">Filter by Status</div>
                  {["Pending Review", "Approved", "Policy Violation"].map(status => (
                    <button 
                      key={status}
                      onClick={() => {
                        setStatusFilter(status === statusFilter ? null : status);
                        setIsFilterOpen(false);
                      }}
                      className={`w-full text-left px-3 py-2 text-sm hover:bg-bg transition-colors ${statusFilter === status ? 'text-primary font-medium' : 'text-text-primary'}`}
                    >
                      {status}
                    </button>
                  ))}
                  {statusFilter && (
                    <button 
                      onClick={() => { setStatusFilter(null); setIsFilterOpen(false); }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-bg transition-colors text-red-500 border-t border-border flex items-center justify-between"
                    >
                      Clear Filter <FilterX size={14} />
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Table Content */}
        <div className="overflow-x-auto min-h-[250px]">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-surface/50 text-text-muted text-xs uppercase tracking-wider border-b border-border">
              <tr>
                <th className="px-6 py-3 font-medium">RFQ ID</th>
                <th className="px-6 py-3 font-medium">Supplier</th>
                <th className="px-6 py-3 font-medium">Total Value</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">AI Recommendation</th>
                <th className="px-6 py-3 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              
              {filteredRFQs.length > 0 ? (
                filteredRFQs.map(rfq => (
                  <tr key={rfq.id} className="hover:bg-bg/50 transition-colors group">
                    <td className="px-6 py-4">
                      <div className="font-medium text-text-primary">{rfq.id}</div>
                      <div className="text-[11px] text-text-muted mt-0.5">{rfq.createdAt}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-text-primary">{rfq.supplier}</div>
                      <div className="text-[11px] text-text-muted mt-0.5">{rfq.title}</div>
                    </td>
                    <td className="px-6 py-4 font-medium text-text-primary">
                      ₺ {parseInt(rfq.value).toLocaleString('en-US')}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1.5 ${rfq.badgeBg} ${rfq.textColor} px-2.5 py-1 rounded-full text-[11px] font-medium border border-border/50`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${rfq.badgeColor}`}></span>
                        {rfq.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex font-medium text-xs ${rfq.aiColor}`}>
                        {rfq.aiStatus}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link 
                        href={`/dashboard/rfq/${rfq.id}`}
                        className="text-primary hover:text-primary-hover font-medium text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        View Details
                      </Link>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-text-muted">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <Search size={24} className="text-border" />
                      <p>No quotes found matching your filters.</p>
                      <button 
                        onClick={() => { setSearchQuery(""); setStatusFilter(null); }}
                        className="text-primary hover:underline text-xs mt-2"
                      >
                        Clear filters
                      </button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div className="px-6 py-3 border-t border-border flex items-center justify-between bg-surface/50">
          <div className="text-xs text-text-muted">
            Showing <span className="font-medium text-text-primary">{filteredRFQs.length > 0 ? 1 : 0}</span> to <span className="font-medium text-text-primary">{filteredRFQs.length}</span> of <span className="font-medium text-text-primary">{filteredRFQs.length}</span> results
          </div>
          <div className="flex items-center gap-2">
            <button className="p-1 rounded border border-border text-text-muted hover:bg-bg disabled:opacity-50" disabled>
              <ChevronLeft size={16} />
            </button>
            <button className="p-1 rounded border border-border text-text-muted hover:bg-bg disabled:opacity-50" disabled={filteredRFQs.length === 0}>
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* ── Upload Modal ────────────────────────────────────────────────── */}
      {isUploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 backdrop-blur-sm p-4">
          <div className="bg-surface-elevated border border-border rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between">
              <h2 className="font-semibold text-text-primary">Upload New Quote</h2>
              <button onClick={() => setIsUploadOpen(false)} className="text-text-muted hover:text-text-primary transition-colors">
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 flex flex-col gap-6">
              <div className="border-2 border-dashed border-border rounded-xl p-8 flex flex-col items-center justify-center text-center hover:border-primary hover:bg-primary/5 transition-colors cursor-pointer group">
                <div className="w-12 h-12 bg-surface rounded-full flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                  <UploadCloud size={24} className="text-text-muted group-hover:text-primary transition-colors" />
                </div>
                <h3 className="text-sm font-medium text-text-primary mb-1">Click to upload or drag and drop</h3>
                <p className="text-xs text-text-muted">PDF, Excel, or Word documents (max 10MB)</p>
              </div>

              <div className="flex flex-col gap-3">
                <label className="text-xs font-semibold text-text-primary">Supplier Name (Optional)</label>
                <input 
                  type="text" 
                  placeholder="Will be auto-extracted by AI if left blank" 
                  className="px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary transition-colors"
                />
              </div>
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface/50 flex justify-end gap-3">
              <button 
                onClick={() => setIsUploadOpen(false)}
                className="px-4 py-2 text-sm font-medium text-text-muted hover:text-text-primary transition-colors"
              >
                Cancel
              </button>
              <button className="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm">
                Analyze Quote
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
