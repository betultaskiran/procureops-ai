"use client";

import React, { useState } from "react";
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
  X
} from "lucide-react";

export default function RFQDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const resolvedParams = React.use(params);
  const rfqId = resolvedParams.id;
  
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
              <h1 className="text-2xl font-semibold tracking-tight text-text-primary">{rfqId}</h1>
              <span className="inline-flex items-center gap-1.5 bg-amber-500/10 text-amber-500 px-2.5 py-1 rounded-full text-[11px] font-medium border border-amber-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                Pending Review
              </span>
            </div>
            <p className="text-sm text-text-muted mt-1">Uploaded on Oct 24, 2026 • by John Doe</p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <button className="flex items-center gap-2 bg-surface-elevated border border-border hover:bg-bg text-text-primary px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm">
            <Download size={16} />
            Original Document
          </button>
          <button 
            onClick={() => setIsConfirmOpen(true)}
            className="flex items-center gap-2 bg-success hover:bg-success/90 text-white px-6 py-2 rounded text-sm font-medium transition-colors shadow-sm"
          >
            <Check size={16} />
            Approve & Create PO
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* ── Left Column: Extraction & Calculation ────────────────────────── */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          
          <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4 flex items-center gap-2">
              <FileText size={16} className="text-primary" />
              Extracted Quote Details
            </h2>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-6">
              <div>
                <div className="text-xs text-text-muted mb-1">Supplier</div>
                <div className="text-sm font-medium text-text-primary">TechCorp Solutions</div>
              </div>
              <div>
                <div className="text-xs text-text-muted mb-1">Payment Terms</div>
                <div className="text-sm font-medium text-text-primary">Net 30</div>
              </div>
              <div>
                <div className="text-xs text-text-muted mb-1">Delivery Time</div>
                <div className="text-sm font-medium text-text-primary">10 Days</div>
              </div>
              <div>
                <div className="text-xs text-text-muted mb-1">Quote Validity</div>
                <div className="text-sm font-medium text-text-primary">Nov 15, 2026</div>
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
                  <tr className="hover:bg-bg/50">
                    <td className="px-4 py-3 text-text-primary">ThinkPad X1 Carbon Gen 11</td>
                    <td className="px-4 py-3 text-right text-text-primary">12</td>
                    <td className="px-4 py-3 text-right text-text-primary">₺ 32,000</td>
                    <td className="px-4 py-3 text-right font-medium text-text-primary">₺ 384,000</td>
                  </tr>
                  <tr className="hover:bg-bg/50">
                    <td className="px-4 py-3 text-text-primary">Dell UltraSharp 27" Monitor</td>
                    <td className="px-4 py-3 text-right text-text-primary">12</td>
                    <td className="px-4 py-3 text-right text-text-primary">₺ 8,500</td>
                    <td className="px-4 py-3 text-right font-medium text-text-primary">₺ 102,000</td>
                  </tr>
                  <tr className="hover:bg-bg/50">
                    <td className="px-4 py-3 text-text-primary">Logitech MX Master 3S</td>
                    <td className="px-4 py-3 text-right text-text-primary">12</td>
                    <td className="px-4 py-3 text-right text-text-primary">₺ 2,100</td>
                    <td className="px-4 py-3 text-right font-medium text-text-primary">₺ 25,200</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Calculation Summary */}
            <div className="mt-6 flex flex-col items-end gap-2 text-sm">
              <div className="flex justify-between w-64 text-text-muted">
                <span>Subtotal:</span>
                <span>₺ 511,200</span>
              </div>
              <div className="flex justify-between w-64 text-text-muted">
                <span>Volume Discount (5%):</span>
                <span className="text-success">- ₺ 25,560</span>
              </div>
              <div className="flex justify-between w-64 text-text-muted border-b border-border pb-2">
                <span>VAT (20%):</span>
                <span>₺ 97,128</span>
              </div>
              <div className="flex justify-between w-64 font-semibold text-text-primary text-base pt-1">
                <span>Total Calculated:</span>
                <span>₺ 582,768</span>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-primary mt-2 bg-primary/10 px-2 py-1 rounded">
                <Calculator size={12} />
                <span>Deterministic math verified. Match: 100%</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Right Column: AI & Policy Guardrails ──────────────────────── */}
        <div className="flex flex-col gap-6">
          
          <div className="bg-surface-elevated border border-border rounded-xl p-6 shadow-sm">
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4 flex items-center gap-2">
              <ShieldCheck size={16} className="text-primary" />
              AI Decision Engine
            </h2>

            <div className="mb-6">
              <div className="text-[10px] uppercase font-bold text-text-muted mb-2 tracking-wider">AI RECOMMENDATION</div>
              <div className="flex items-center gap-2 text-lg font-semibold text-text-primary">
                Recommended
              </div>
              <div className="text-xs text-text-muted mt-1">Review 1 warning before approval.</div>
            </div>

            <div className="mb-6">
              <div className="text-[10px] uppercase font-bold text-text-muted mb-2 tracking-wider">Why?</div>
              <div className="space-y-3">
                <div className="flex gap-2 items-start">
                  <CheckCircle size={14} className="text-success mt-0.5 shrink-0" />
                  <div className="text-xs text-text-primary">Within approved <span className="font-medium">IT Hardware Budget</span> (₺1.2M remaining)</div>
                </div>
                <div className="flex gap-2 items-start">
                  <CheckCircle size={14} className="text-success mt-0.5 shrink-0" />
                  <div className="text-xs text-text-primary">TechCorp is an <span className="font-medium">Approved Vendor</span> (Active in SAP)</div>
                </div>
                <div className="flex gap-2 items-start">
                  <CheckCircle size={14} className="text-success mt-0.5 shrink-0" />
                  <div className="text-xs text-text-primary"><span className="font-medium">Payment Terms</span> match standard Net 30</div>
                </div>
                <div className="flex gap-2 items-start">
                  <AlertTriangle size={14} className="text-amber-500 mt-0.5 shrink-0" />
                  <div className="text-xs text-text-primary"><span className="font-medium">Delivery (10 Days)</span> exceeds preferred SLA (7 Days)</div>
                </div>
              </div>
            </div>

            <div>
              <div className="text-[10px] uppercase font-bold text-text-muted mb-2 tracking-wider">Evidence Links</div>
              <div className="flex flex-wrap gap-2">
                <button className="text-[10px] bg-bg border border-border px-2 py-1.5 rounded hover:bg-surface transition-colors text-text-primary flex items-center gap-1 font-medium">
                  <FileText size={10} className="text-primary" /> Original Quote
                </button>
                <button className="text-[10px] bg-bg border border-border px-2 py-1.5 rounded hover:bg-surface transition-colors text-text-primary flex items-center gap-1 font-medium">
                  <ShieldCheck size={10} className="text-primary" /> Policy #SLA-04
                </button>
                <button className="text-[10px] bg-bg border border-border px-2 py-1.5 rounded hover:bg-surface transition-colors text-text-primary flex items-center gap-1 font-medium">
                  <Calculator size={10} className="text-primary" /> SAP Budget
                </button>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm text-white">
            <h2 className="text-sm font-semibold uppercase tracking-wider mb-2 flex items-center gap-2">
              <Mail size={16} className="text-primary" />
              Next Step: Dispatch
            </h2>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              If approved, the system will automatically generate a PDF Purchase Order and send an email to 
              <span className="text-slate-200 font-medium"> sales@techcorp.com</span>.
            </p>
            <div className="bg-slate-800 rounded p-3 text-xs font-mono text-slate-300 border border-slate-700">
              Subject: Purchase Order PO-2026-9922<br/>
              Attached: PO-2026-9922.pdf
            </div>
          </div>

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
                  <span className="font-medium text-text-primary">TechCorp Solutions</span>
                </div>
                <div className="flex justify-between mb-2">
                  <span className="text-text-muted">Total Value (TCO):</span>
                  <span className="font-medium text-text-primary">₺ 582,768</span>
                </div>
                <div className="flex justify-between mb-2">
                  <span className="text-text-muted">AI Recommendation:</span>
                  <span className="font-medium text-text-primary">Recommended</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Warnings:</span>
                  <span className="font-medium text-amber-500">1 (Delivery Timeline)</span>
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
            </div>

            <div className="px-6 py-4 border-t border-border bg-surface/50 flex justify-end gap-3">
              <button 
                onClick={() => setIsConfirmOpen(false)}
                className="px-4 py-2 text-sm font-medium text-text-muted hover:text-text-primary transition-colors"
              >
                Cancel
              </button>
              <button className="bg-success hover:bg-success/90 text-white px-4 py-2 rounded text-sm font-medium transition-colors shadow-sm">
                Approve & Create PO
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
