"use client";

import React, { useState, useEffect, useMemo } from "react";
import { 
  Users, 
  UserPlus, 
  Shield, 
  ShieldCheck, 
  ShieldAlert, 
  CheckCircle2, 
  AlertCircle, 
  Search, 
  RefreshCw, 
  UserCheck, 
  UserX, 
  Mail, 
  Lock, 
  X, 
  Key,
  Eye,
  EyeOff
} from "lucide-react";
import { teamApi } from "@/lib/api/team";
import { TeamMember, UserRole, AuthMeResponse } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthContext";
import { useTranslation } from "@/lib/i18n";
import { formatDate as fmtDate } from "@/lib/i18n/formatters";

export default function TeamManagementPage() {
  const { user: authUser } = useAuth();
  const { t, locale } = useTranslation();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [currentUser, setCurrentUser] = useState<AuthMeResponse | null>(authUser);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const getRoleInfo = (role: UserRole) => {
    switch (role) {
      case "admin":
        return {
          label: t("team_page.roles.admin.label"),
          desc: t("team_page.roles.admin.desc"),
          badgeClass: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20",
        };
      case "manager":
        return {
          label: t("team_page.roles.manager.label"),
          desc: t("team_page.roles.manager.desc"),
          badgeClass: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
        };
      case "purchasing_director":
        return {
          label: t("team_page.roles.purchasing_director.label"),
          desc: t("team_page.roles.purchasing_director.desc"),
          badgeClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
        };
      case "cfo":
        return {
          label: t("team_page.roles.cfo.label"),
          desc: t("team_page.roles.cfo.desc"),
          badgeClass: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20",
        };
      case "employee":
        return {
          label: t("team_page.roles.employee.label"),
          desc: t("team_page.roles.employee.desc"),
          badgeClass: "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20",
        };
      case "viewer":
        return {
          label: t("team_page.roles.viewer.label"),
          desc: t("team_page.roles.viewer.desc"),
          badgeClass: "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20",
        };
    }
  };

  useEffect(() => {
    if (authUser) {
      setCurrentUser(authUser);
    }
  }, [authUser]);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Modals state
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Form state
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("employee");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // Confirmation modals
  const [deactivatingMember, setDeactivatingMember] = useState<TeamMember | null>(null);
  const [reactivatingMember, setReactivatingMember] = useState<TeamMember | null>(null);
  const [roleChangeMember, setRoleChangeMember] = useState<TeamMember | null>(null);
  const [newSelectedRole, setNewSelectedRole] = useState<UserRole>("employee");
  const [modalActionError, setModalActionError] = useState<string | null>(null);

  // Fetch team members and current user info
  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      try {
        const user = await teamApi.getCurrentUser();
        setCurrentUser(user);
      } catch {
        // Dev fallback
      }

      const teamList = await teamApi.getMembers();
      setMembers(teamList);
    } catch (err: any) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Error loading team members.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Filtered members list
  const filteredMembers = useMemo(() => {
    return members.filter((m) => {
      const matchesSearch = 
        m.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.email.toLowerCase().includes(searchQuery.toLowerCase());
      
      const matchesRole = roleFilter === "all" || m.role === roleFilter;
      const matchesStatus = 
        statusFilter === "all" || 
        (statusFilter === "active" && m.is_active) || 
        (statusFilter === "inactive" && !m.is_active);

      return matchesSearch && matchesRole && matchesStatus;
    });
  }, [members, searchQuery, roleFilter, statusFilter]);

  // Derived counts
  const totalCount = members.length;
  const activeCount = members.filter((m) => m.is_active).length;
  const adminCount = members.filter((m) => m.role === "admin" && m.is_active).length;

  const isAdmin = currentUser?.role === "admin";

  // Handle Add Member
  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddError(null);

    if (password.length < 8) {
      setAddError("Password must be at least 8 characters.");
      return;
    }

    try {
      setIsSubmitting(true);
      const newMember = await teamApi.createMember({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        role,
        password,
      });

      setMembers((prev) => [...prev, newMember]);
      setIsAddModalOpen(false);
      setFullName("");
      setEmail("");
      setPassword("");
      setRole("employee");
      setActionSuccess(t("team_page.toast_member_added"));
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setAddError(err?.message || "Failed to add user.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Role Update
  const handleConfirmRoleChange = async () => {
    if (!roleChangeMember) return;
    setModalActionError(null);
    try {
      setIsSubmitting(true);
      const updated = await teamApi.updateRole(roleChangeMember.id, { role: newSelectedRole });
      setMembers((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      setRoleChangeMember(null);
      setActionSuccess(t("team_page.toast_member_updated"));
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setModalActionError(err?.message || "Failed to update role.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Deactivation
  const handleConfirmDeactivate = async () => {
    if (!deactivatingMember) return;
    setModalActionError(null);
    try {
      setIsSubmitting(true);
      const updated = await teamApi.deactivateMember(deactivatingMember.id);
      setMembers((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      setDeactivatingMember(null);
      setActionSuccess(t("team_page.toast_member_updated"));
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setModalActionError(err?.message || "Failed to deactivate member.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Reactivation
  const handleConfirmReactivate = async () => {
    if (!reactivatingMember) return;
    setModalActionError(null);
    try {
      setIsSubmitting(true);
      const updated = await teamApi.reactivateMember(reactivatingMember.id);
      setMembers((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      setReactivatingMember(null);
      setActionSuccess(t("team_page.toast_member_updated"));
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setModalActionError(err?.message || "Failed to reactivate member.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-primary/10 text-primary border border-primary/20">
              <Users size={24} />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-text-primary tracking-tight">
                {t("team_page.title")}
              </h1>
              <p className="text-sm text-text-muted mt-1">
                {t("team_page.subtitle")}
              </p>
            </div>
          </div>
        </div>

        {isAdmin && (
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-semibold transition-colors shadow-sm self-start md:self-auto"
          >
            <UserPlus size={16} />
            <span>{t("team_page.add_member_btn")}</span>
          </button>
        )}
      </div>

      {/* ── Toast Feedback ──────────────────────────────────────────────── */}
      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-sm flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 size={18} className="shrink-0" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-emerald-500 hover:text-emerald-700">
            <X size={16} />
          </button>
        </div>
      )}

      {/* ── Filters Bar ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-surface border border-border p-3.5 rounded-xl">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("team_page.search_placeholder")}
            className="w-full pl-10 pr-4 py-2 text-xs bg-surface-elevated border border-border rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        <div className="flex items-center gap-2">
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="px-3 py-2 text-xs bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none"
          >
            <option value="all">{t("team_page.filter_all_roles")}</option>
            <option value="admin">{t("team_page.roles.admin.label")}</option>
            <option value="manager">{t("team_page.roles.manager.label")}</option>
            <option value="purchasing_director">{t("team_page.roles.purchasing_director.label")}</option>
            <option value="cfo">{t("team_page.roles.cfo.label")}</option>
            <option value="employee">{t("team_page.roles.employee.label")}</option>
            <option value="viewer">{t("team_page.roles.viewer.label")}</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 text-xs bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none"
          >
            <option value="all">{t("team_page.filter_all_statuses")}</option>
            <option value="active">{t("team_page.status_active")}</option>
            <option value="inactive">{t("team_page.status_inactive")}</option>
          </select>
        </div>
      </div>

      {/* ── Members Table ───────────────────────────────────────────────── */}
      <div className="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-16 flex flex-col items-center justify-center gap-3">
            <RefreshCw size={24} className="animate-spin text-primary" />
            <span className="text-xs text-text-muted">Loading team members...</span>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-rose-500 text-xs">
            {error}
          </div>
        ) : filteredMembers.length === 0 ? (
          <div className="p-16 text-center text-text-muted space-y-2">
            <Users size={32} className="mx-auto opacity-40" />
            <p className="text-sm font-medium text-text-primary">{t("team_page.no_members_found")}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-surface-elevated/50 text-text-muted uppercase text-[10px] tracking-wider border-b border-border">
                <tr>
                  <th className="p-4 font-semibold">{t("team_page.th_member")}</th>
                  <th className="p-4 font-semibold">{t("team_page.th_role")}</th>
                  <th className="p-4 font-semibold">{t("team_page.th_status")}</th>
                  <th className="p-4 font-semibold">{t("team_page.table_joined")}</th>
                  {isAdmin && <th className="p-4 font-semibold text-right">{t("team_page.th_actions")}</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredMembers.map((member) => {
                  const roleConfig = getRoleInfo(member.role);
                  const isCurrent = currentUser?.email === member.email;

                  return (
                    <tr key={member.id} className="hover:bg-surface-elevated/30 transition-colors">
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center font-bold text-xs text-primary">
                            {member.full_name.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div className="font-semibold text-text-primary flex items-center gap-2">
                              <span>{member.full_name}</span>
                              {isCurrent && (
                                <span className="text-[10px] px-1.5 py-0.2 rounded bg-surface-elevated border border-border text-primary font-medium">
                                  You
                                </span>
                              )}
                            </div>
                            <span className="text-text-muted text-[11px]">{member.email}</span>
                          </div>
                        </div>
                      </td>

                      <td className="p-4">
                        <span className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${roleConfig.badgeClass}`}>
                          {roleConfig.label}
                        </span>
                      </td>

                      <td className="p-4">
                        {member.is_active ? (
                          <span className="inline-flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium text-xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            {t("team_page.status_active")}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-rose-500 font-medium text-xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                            {t("team_page.status_inactive")}
                          </span>
                        )}
                      </td>

                      <td className="p-4 text-text-muted">
                        {fmtDate(member.created_at, locale)}
                      </td>

                      {isAdmin && (
                        <td className="p-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => {
                                setRoleChangeMember(member);
                                setNewSelectedRole(member.role);
                                setModalActionError(null);
                              }}
                              className="px-2.5 py-1 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-elevated border border-border rounded-lg transition-colors"
                            >
                              {t("team_page.btn_change_role")}
                            </button>

                            {member.is_active ? (
                              <button
                                onClick={() => {
                                  setDeactivatingMember(member);
                                  setModalActionError(null);
                                }}
                                disabled={isCurrent || (member.role === "admin" && adminCount <= 1)}
                                className="px-2.5 py-1 text-xs font-medium text-rose-600 hover:text-rose-700 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                                title={isCurrent ? "Cannot deactivate own account" : undefined}
                              >
                                {t("team_page.btn_deactivate")}
                              </button>
                            ) : (
                              <button
                                onClick={() => {
                                  setReactivatingMember(member);
                                  setModalActionError(null);
                                }}
                                className="px-2.5 py-1 text-xs font-medium text-emerald-600 hover:text-emerald-700 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 rounded-lg transition-colors"
                              >
                                {t("team_page.btn_reactivate")}
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Modal: Add Member ────────────────────────────────────────────── */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-border shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="font-bold text-text-primary text-base">{t("team_page.modal_add_title")}</h3>
              <button onClick={() => setIsAddModalOpen(false)} className="text-text-muted hover:text-text-primary">
                <X size={18} />
              </button>
            </div>

            {addError && (
              <div className="p-3 text-xs rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400">
                {addError}
              </div>
            )}

            <form onSubmit={handleAddMember} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-text-primary mb-1">
                  {t("team_page.modal_full_name")} *
                </label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>

              <div>
                <label className="block font-semibold text-text-primary mb-1">
                  {t("team_page.modal_email")} *
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>

              <div>
                <label className="block font-semibold text-text-primary mb-1">
                  {t("team_page.modal_role")} *
                </label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as UserRole)}
                  className="w-full px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
                >
                  <option value="admin">{t("team_page.roles.admin.label")}</option>
                  <option value="manager">{t("team_page.roles.manager.label")}</option>
                  <option value="purchasing_director">{t("team_page.roles.purchasing_director.label")}</option>
                  <option value="cfo">{t("team_page.roles.cfo.label")}</option>
                  <option value="employee">{t("team_page.roles.employee.label")}</option>
                  <option value="viewer">{t("team_page.roles.viewer.label")}</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-text-primary mb-1">
                  {t("team_page.modal_password")} *
                </label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>

              <div className="pt-3 flex items-center justify-end gap-2 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 font-medium text-text-muted hover:text-text-primary bg-surface-elevated border border-border rounded-lg transition-colors"
                >
                  {t("team_page.modal_cancel")}
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 font-semibold text-white bg-primary hover:bg-primary-hover rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  {isSubmitting && <RefreshCw size={14} className="animate-spin" />}
                  <span>{isSubmitting ? t("team_page.modal_saving") : t("team_page.modal_save_btn")}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Change Role ───────────────────────────────────────────── */}
      {roleChangeMember && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-border shadow-xl max-w-sm w-full p-5 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-primary/10 text-primary">
                <Shield size={20} />
              </div>
              <div>
                <h3 className="font-bold text-text-primary text-base">{t("team_page.confirm_role_title")}</h3>
                <p className="text-xs text-text-muted">{roleChangeMember.full_name}</p>
              </div>
            </div>

            {modalActionError && (
              <div className="p-3 text-xs rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 flex items-center gap-2">
                <AlertCircle size={14} className="shrink-0" />
                <span>{modalActionError}</span>
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-text-primary mb-1">
                {t("team_page.confirm_role_desc", { name: roleChangeMember.full_name })}
              </label>
              <select
                value={newSelectedRole}
                onChange={(e) => setNewSelectedRole(e.target.value as UserRole)}
                className="w-full px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                <option value="admin">{t("team_page.roles.admin.label")}</option>
                <option value="manager">{t("team_page.roles.manager.label")}</option>
                <option value="purchasing_director">{t("team_page.roles.purchasing_director.label")}</option>
                <option value="cfo">{t("team_page.roles.cfo.label")}</option>
                <option value="employee">{t("team_page.roles.employee.label")}</option>
                <option value="viewer">{t("team_page.roles.viewer.label")}</option>
              </select>
            </div>

            <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
              <button
                onClick={() => setRoleChangeMember(null)}
                className="px-3.5 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-elevated border border-border rounded-lg"
              >
                {t("team_page.modal_cancel")}
              </button>
              <button
                onClick={handleConfirmRoleChange}
                disabled={isSubmitting || newSelectedRole === roleChangeMember.role}
                className="px-3.5 py-1.5 text-xs font-semibold text-white bg-primary hover:bg-primary-hover rounded-lg disabled:opacity-50 flex items-center gap-1.5"
              >
                {isSubmitting && <RefreshCw size={14} className="animate-spin" />}
                <span>{t("team_page.btn_change_role")}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Deactivate Confirmation ──────────────────────────────── */}
      {deactivatingMember && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-border shadow-xl max-w-sm w-full p-5 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-rose-500/10 text-rose-500">
                <UserX size={20} />
              </div>
              <div>
                <h3 className="font-bold text-text-primary text-base">{t("team_page.confirm_deactivate_title")}</h3>
                <p className="text-xs text-text-muted">{deactivatingMember.full_name}</p>
              </div>
            </div>

            {modalActionError && (
              <div className="p-3 text-xs rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 flex items-center gap-2">
                <AlertCircle size={14} className="shrink-0" />
                <span>{modalActionError}</span>
              </div>
            )}

            <p className="text-xs text-text-secondary leading-relaxed">
              {t("team_page.confirm_deactivate_desc", { name: deactivatingMember.full_name })}
            </p>

            <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
              <button
                onClick={() => setDeactivatingMember(null)}
                className="px-3.5 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-elevated border border-border rounded-lg"
              >
                {t("team_page.modal_cancel")}
              </button>
              <button
                onClick={handleConfirmDeactivate}
                disabled={isSubmitting}
                className="px-3.5 py-1.5 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg disabled:opacity-50 flex items-center gap-1.5"
              >
                {isSubmitting && <RefreshCw size={14} className="animate-spin" />}
                <span>{t("team_page.btn_deactivate")}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Reactivate Confirmation ──────────────────────────────── */}
      {reactivatingMember && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-border shadow-xl max-w-sm w-full p-5 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-emerald-500/10 text-emerald-500">
                <UserCheck size={20} />
              </div>
              <div>
                <h3 className="font-bold text-text-primary text-base">{t("team_page.confirm_reactivate_title")}</h3>
                <p className="text-xs text-text-muted">{reactivatingMember.full_name}</p>
              </div>
            </div>

            {modalActionError && (
              <div className="p-3 text-xs rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 flex items-center gap-2">
                <AlertCircle size={14} className="shrink-0" />
                <span>{modalActionError}</span>
              </div>
            )}

            <p className="text-xs text-text-secondary leading-relaxed">
              {t("team_page.confirm_reactivate_desc", { name: reactivatingMember.full_name })}
            </p>

            <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
              <button
                onClick={() => setReactivatingMember(null)}
                className="px-3.5 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-elevated border border-border rounded-lg"
              >
                {t("team_page.modal_cancel")}
              </button>
              <button
                onClick={handleConfirmReactivate}
                disabled={isSubmitting}
                className="px-3.5 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg disabled:opacity-50 flex items-center gap-1.5"
              >
                {isSubmitting && <RefreshCw size={14} className="animate-spin" />}
                <span>{t("team_page.btn_reactivate")}</span>
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
