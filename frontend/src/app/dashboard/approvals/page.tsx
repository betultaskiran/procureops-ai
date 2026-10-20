"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { 
  CheckSquare, 
  CheckCircle2, 
  XCircle, 
  AlertTriangle, 
  Clock, 
  Loader2, 
  Building2, 
  DollarSign, 
  ShieldAlert, 
  ChevronRight, 
  MessageSquare, 
  ExternalLink,
  ShieldCheck,
  UserCheck
} from "lucide-react";
import { useAuth } from "@/lib/auth/AuthContext";
import { ordersApi } from "@/lib/api/orders";
import { PendingApprovalItemResponse } from "@/lib/api/types";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency as fmtCurrency, formatDate as fmtDate } from "@/lib/i18n/formatters";

export default function ApprovalsQueuePage() {
  const { user } = useAuth();
  const { t, locale } = useTranslation();
  const [items, setItems] = useState<PendingApprovalItemResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modal states
  const [approvingItem, setApprovingItem] = useState<PendingApprovalItemResponse | null>(null);
  const [approveComment, setApproveComment] = useState("");
  const [isSubmittingApprove, setIsSubmittingApprove] = useState(false);

  const [rejectingItem, setRejectingItem] = useState<PendingApprovalItemResponse | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectError, setRejectError] = useState<string | null>(null);
  const [isSubmittingReject, setIsSubmittingReject] = useState(false);

  const fetchApprovals = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await ordersApi.getPendingApprovals();
      setItems(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error loading approval queue.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchApprovals();
  }, [fetchApprovals]);

  const handleApprove = async () => {
    if (!approvingItem) return;
    setIsSubmittingApprove(true);
    setError(null);
    try {
      await ordersApi.approveStep(
        approvingItem.purchase_order_id,
        approvingItem.step_id,
        approveComment
      );
      setSuccessMsg(t("approvals_page.toast_approved", { po: approvingItem.po_number }));
      setApprovingItem(null);
      setApproveComment("");
      await fetchApprovals();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Approval operation failed.";
      setError(msg);
    } finally {
      setIsSubmittingApprove(false);
    }
  };

  const handleReject = async () => {
    if (!rejectingItem) return;
    if (!rejectReason.trim() || rejectReason.trim().length < 3) {
      setRejectError(t("approvals_page.err_min_reject_length"));
      return;
    }
    setIsSubmittingReject(true);
    setRejectError(null);
    try {
      await ordersApi.rejectStep(
        rejectingItem.purchase_order_id,
        rejectingItem.step_id,
        rejectReason.trim()
      );
      setSuccessMsg(t("approvals_page.toast_rejected", { po: rejectingItem.po_number }));
      setRejectingItem(null);
      setRejectReason("");
      await fetchApprovals();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Rejection failed.";
      setRejectError(msg);
    } finally {
      setIsSubmittingReject(false);
    }
  };

  const formatCurrency = (val: number, cur: string) => {
    return fmtCurrency(val, cur || "TRY", locale);
  };

  const getRoleLabel = (role: string) => {
    switch (role) {
      case "purchasing_director":
        return t("approvals_page.roles.purchasing_director");
      case "cfo":
        return t("approvals_page.roles.cfo");
      case "admin":
        return t("approvals_page.roles.admin");
      case "manager":
        return t("approvals_page.roles.manager");
      case "employee":
        return t("approvals_page.roles.employee");
      case "viewer":
        return t("approvals_page.roles.viewer");
      default:
        return role;
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-primary/10 text-primary border border-primary/20">
              <CheckSquare size={24} />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-text-primary tracking-tight">
                {t("approvals_page.title")}
              </h1>
              <p className="text-sm text-text-muted mt-1">
                {t("approvals_page.subtitle")}
              </p>
            </div>
          </div>
        </div>

        {/* Current User Role Pill */}
        {user && (
          <div className="flex items-center gap-2 self-start md:self-auto px-3.5 py-1.5 rounded-full border border-border bg-surface-elevated text-xs font-medium text-text-primary">
            <UserCheck size={14} className="text-primary" />
            <span>{t("approvals_page.your_authority")}</span>
            <span className="font-semibold text-primary">{getRoleLabel(user.role)}</span>
          </div>
        )}
      </div>

      {/* ── Status Alerts ────────────────────────────────────────────────────── */}
      {error && (
        <div className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 text-sm flex items-start gap-3">
          <AlertTriangle size={18} className="shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium">{t("approvals_page.error_title")}</p>
            <p className="text-xs mt-0.5">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="text-rose-500 hover:text-rose-700 text-xs">
            {t("approvals_page.close")}
          </button>
        </div>
      )}

      {successMsg && (
        <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-sm flex items-start gap-3">
          <CheckCircle2 size={18} className="shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium">{t("approvals_page.success_title")}</p>
            <p className="text-xs mt-0.5">{successMsg}</p>
          </div>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-500 hover:text-emerald-700 text-xs">
            {t("approvals_page.close")}
          </button>
        </div>
      )}

      {/* ── Content Section ─────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="p-16 flex flex-col items-center justify-center gap-3 bg-surface rounded-xl border border-border">
          <Loader2 size={32} className="animate-spin text-primary" />
          <span className="text-sm text-text-muted">{t("approvals_page.loading_queue")}</span>
        </div>
      ) : items.length === 0 ? (
        <div className="p-16 flex flex-col items-center justify-center gap-4 bg-surface rounded-xl border border-border text-center">
          <div className="h-16 w-16 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center border border-emerald-500/20">
            <CheckCircle2 size={32} />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-text-primary">{t("approvals_page.empty_title")}</h3>
            <p className="text-sm text-text-muted max-w-md mt-1">
              {user?.role === "purchasing_director" || user?.role === "cfo" || user?.role === "admin"
                ? t("approvals_page.empty_desc_approver")
                : t("approvals_page.empty_desc_unauthorized")}
            </p>
          </div>
          <Link
            href="/dashboard/quotes"
            className="mt-2 inline-flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-md bg-surface-elevated hover:bg-border text-text-primary transition-colors"
          >
            {t("approvals_page.view_all_quotes")}
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="text-xs font-medium text-text-muted px-1 flex items-center justify-between">
            <span>{t("approvals_page.pending_count_info", { count: items.length })}</span>
            <span className="text-amber-500 font-semibold">{t("approvals_page.draft_notice")}</span>
          </div>

          <div className="grid grid-cols-1 gap-4">
            {items.map((item) => (
              <div
                key={item.step_id}
                className="bg-surface border border-border hover:border-border-focus rounded-xl p-6 transition-all shadow-sm space-y-4"
              >
                {/* Card Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/60 pb-4">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm font-bold text-text-primary bg-surface-elevated px-2.5 py-1 rounded border border-border">
                      {item.po_number}
                    </span>
                    <span className="text-xs px-2.5 py-0.5 rounded-full border bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 font-medium flex items-center gap-1.5">
                      <Clock size={12} />
                      {t("approvals_page.awaiting_role_approval", { role: getRoleLabel(item.role) })}
                    </span>
                  </div>

                  <div className="text-right">
                    <div className="text-lg font-bold text-text-primary">
                      {formatCurrency(item.amount, item.currency)}
                    </div>
                    <span className="text-[11px] text-text-muted">{t("approvals_page.total_order_amount")}</span>
                  </div>
                </div>

                {/* Details Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 text-xs">
                  <div>
                    <span className="text-text-muted block mb-1">{t("approvals_page.supplier_label")}</span>
                    <span className="font-semibold text-text-primary flex items-center gap-1.5 text-sm">
                      <Building2 size={14} className="text-text-muted shrink-0" />
                      {item.supplier_name}
                    </span>
                  </div>

                  <div>
                    <span className="text-text-muted block mb-1">{t("approvals_page.linked_rfq_label")}</span>
                    <Link
                      href={`/dashboard/rfq/${item.rfq_id}`}
                      className="font-semibold text-primary hover:underline flex items-center gap-1 text-sm"
                    >
                      {item.rfq_title}
                      <ExternalLink size={12} />
                    </Link>
                  </div>

                  <div>
                    <span className="text-text-muted block mb-1">{t("approvals_page.request_created_date")}</span>
                    <span className="text-text-primary font-medium">
                      {fmtDate(item.created_at, locale)}
                    </span>
                  </div>
                </div>

                {/* Multi-Tier Progress Indicator */}
                <div className="pt-2 border-t border-border/40">
                  <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wider block mb-2">
                    {t("approvals_page.tiers_progress_title")}
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {item.all_steps.map((step) => {
                      const isTarget = step.id === item.step_id;
                      const isApproved = step.status === "approved";
                      const isRejected = step.status === "rejected";

                      return (
                        <div
                          key={step.id}
                          className={`p-3 rounded-lg border flex items-center justify-between text-xs transition-colors ${
                            isApproved
                              ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-600 dark:text-emerald-400"
                              : isRejected
                              ? "bg-rose-500/5 border-rose-500/20 text-rose-600 dark:text-rose-400"
                              : isTarget
                              ? "bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-300 ring-1 ring-amber-500/20"
                              : "bg-surface-elevated/40 border-border text-text-muted"
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            {isApproved ? (
                              <CheckCircle2 size={16} className="text-emerald-500" />
                            ) : isRejected ? (
                              <XCircle size={16} className="text-rose-500" />
                            ) : (
                              <Clock size={16} className={isTarget ? "text-amber-500" : "text-text-muted"} />
                            )}
                            <div>
                              <div className="font-semibold">{getRoleLabel(step.role)}</div>
                              <div className="text-[10px] text-text-muted">
                                {isApproved
                                  ? t("approvals_page.approver_note", {
                                      name: step.approver_name || "Yetkili",
                                      date: step.decision_at ? fmtDate(step.decision_at, locale) : ""
                                    })
                                  : isRejected
                                  ? t("approvals_page.rejected_note", { reason: step.rejection_reason || "" })
                                  : t("approvals_page.pending_step")}
                              </div>
                            </div>
                          </div>

                          {isTarget && (
                            <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-700 dark:text-amber-300">
                              {t("approvals_page.your_step")}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="pt-2 flex items-center justify-end gap-3">
                  <button
                    onClick={() => {
                      setRejectingItem(item);
                      setRejectReason("");
                      setRejectError(null);
                    }}
                    className="px-4 py-2 rounded-lg text-xs font-semibold border border-rose-500/20 text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 transition-colors flex items-center gap-1.5"
                  >
                    <XCircle size={14} />
                    {t("approvals_page.reject_order_btn")}
                  </button>

                  <button
                    onClick={() => {
                      setApprovingItem(item);
                      setApproveComment("");
                    }}
                    className="px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition-colors flex items-center gap-1.5 shadow-sm"
                  >
                    <CheckCircle2 size={14} />
                    {t("approvals_page.approve_role_btn", { role: getRoleLabel(item.role) })}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Approve Modal ───────────────────────────────────────────────────── */}
      {approvingItem && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-surface border border-border rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                <ShieldCheck size={22} />
              </div>
              <div>
                <h3 className="text-base font-bold text-text-primary">{t("approvals_page.modal_approve_title")}</h3>
                <p className="text-xs text-text-muted">
                  {t("approvals_page.modal_approve_subtitle", { po: approvingItem.po_number, role: getRoleLabel(approvingItem.role) })}
                </p>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-surface-elevated border border-border text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-text-muted">{t("approvals_page.supplier_label")}:</span>
                <span className="font-semibold text-text-primary">{approvingItem.supplier_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">{t("approvals_page.total_order_amount")}:</span>
                <span className="font-semibold text-text-primary">
                  {formatCurrency(approvingItem.amount, approvingItem.currency)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">{t("approvals_page.modal_role_label")}</span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                  {getRoleLabel(approvingItem.role)}
                </span>
              </div>
            </div>

            <p className="text-xs text-text-muted">
              {t("approvals_page.modal_approve_legal_note")}
            </p>

            <div>
              <label className="text-xs font-semibold text-text-primary block mb-1">
                {t("approvals_page.modal_approve_note_label")}
              </label>
              <textarea
                value={approveComment}
                onChange={(e) => setApproveComment(e.target.value)}
                placeholder={t("approvals_page.modal_approve_note_placeholder")}
                rows={3}
                className="w-full text-xs p-3 rounded-lg bg-surface-elevated border border-border focus:outline-none focus:ring-1 focus:ring-primary text-text-primary"
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setApprovingItem(null)}
                disabled={isSubmittingApprove}
                className="px-4 py-2 rounded-lg text-xs font-medium border border-border text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
              >
                {t("approvals_page.modal_cancel_btn")}
              </button>
              <button
                type="button"
                onClick={handleApprove}
                disabled={isSubmittingApprove}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition-colors flex items-center gap-1.5"
              >
                {isSubmittingApprove ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>{t("approvals_page.modal_approving_btn")}</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={14} />
                    <span>{t("approvals_page.modal_confirm_approve_btn")}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Reject Modal ────────────────────────────────────────────────────── */}
      {rejectingItem && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-surface border border-border rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/20">
                <ShieldAlert size={22} />
              </div>
              <div>
                <h3 className="text-base font-bold text-text-primary">{t("approvals_page.modal_reject_title")}</h3>
                <p className="text-xs text-text-muted">
                  {t("approvals_page.modal_reject_subtitle", { po: rejectingItem.po_number, role: getRoleLabel(rejectingItem.role) })}
                </p>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-rose-500/5 border border-rose-500/20 text-xs text-rose-600 dark:text-rose-400 space-y-1">
              <p className="font-semibold">{t("approvals_page.modal_reject_warning_title")}</p>
              <p>
                {t("approvals_page.modal_reject_warning_desc")}
              </p>
            </div>

            <div>
              <label className="text-xs font-semibold text-text-primary block mb-1">
                {t("approvals_page.modal_reject_reason_label")} <span className="text-rose-500">*</span>
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => {
                  setRejectReason(e.target.value);
                  if (rejectError) setRejectError(null);
                }}
                placeholder={t("approvals_page.modal_reject_reason_placeholder")}
                rows={3}
                className="w-full text-xs p-3 rounded-lg bg-surface-elevated border border-border focus:outline-none focus:ring-1 focus:ring-rose-500 text-text-primary"
              />
              {rejectError && <p className="text-[11px] text-rose-500 mt-1">{rejectError}</p>}
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setRejectingItem(null)}
                disabled={isSubmittingReject}
                className="px-4 py-2 rounded-lg text-xs font-medium border border-border text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
              >
                {t("approvals_page.modal_cancel_btn")}
              </button>
              <button
                type="button"
                onClick={handleReject}
                disabled={isSubmittingReject}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white transition-colors flex items-center gap-1.5"
              >
                {isSubmittingReject ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>{t("approvals_page.modal_rejecting_btn")}</span>
                  </>
                ) : (
                  <>
                    <XCircle size={14} />
                    <span>{t("approvals_page.modal_confirm_reject_btn")}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
