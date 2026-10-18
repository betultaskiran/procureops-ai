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

// Role configuration
const ROLE_CONFIG: Record<UserRole, { label: string; desc: string; badgeClass: string }> = {
  admin: {
    label: "Yönetici (Admin)",
    desc: "Tüm organizasyonu, politikaları ve ekip üyelerini yönetir",
    badgeClass: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20",
  },
  manager: {
    label: "Satın Alma Yöneticisi",
    desc: "Teklif onaylarını ve satınalma siparişlerini yönetir",
    badgeClass: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
  },
  purchasing_director: {
    label: "Satın Alma Direktörü",
    desc: "Yüksek tutarlı siparişleri ve kurumsal satınalma süreçlerini onaylar",
    badgeClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  },
  cfo: {
    label: "Mali İşler Direktörü (CFO)",
    desc: "250.000 TL üzerindeki harcamaların finansal uygunluğunu onaylar",
    badgeClass: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20",
  },
  employee: {
    label: "Satın Alma Uzmanı",
    desc: "RFQ oluşturur, teklif yükler ve analiz çalıştırır",
    badgeClass: "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20",
  },
  viewer: {
    label: "Gözlemci (Viewer)",
    desc: "Tüm süreçleri salt-okunur olarak görüntüler",
    badgeClass: "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20",
  },
};

export default function TeamManagementPage() {
  const { user: authUser } = useAuth();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [currentUser, setCurrentUser] = useState<AuthMeResponse | null>(authUser);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

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

      // Attempt to get current user details
      try {
        const user = await teamApi.getCurrentUser();
        setCurrentUser(user);
      } catch {
        // Fallback or unauthenticated in standalone dev
      }

      const teamList = await teamApi.getMembers();
      setMembers(teamList);
    } catch (err: any) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Ekip üyeleri yüklenirken bir sorun oluştu.");
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
      setAddError("Şifre en az 8 karakter olmalıdır.");
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
      setActionSuccess(`${newMember.full_name} başarıyla ekibe eklendi.`);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setAddError(err?.message || "Kullanıcı eklenirken bir hata oluştu.");
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
      setActionSuccess(`${updated.full_name} kullanıcısının rolü "${ROLE_CONFIG[newSelectedRole].label}" olarak güncellendi.`);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setModalActionError(err?.message || "Rol güncellenirken hata oluştu.");
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
      setActionSuccess(`${updated.full_name} pasife alındı.`);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setModalActionError(err?.message || "Kullanıcı pasife alınırken hata oluştu.");
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
      setActionSuccess(`${updated.full_name} yeniden aktifleştirildi.`);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err: any) {
      setModalActionError(err?.message || "Kullanıcı aktifleştirilirken hata oluştu.");
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
              <h1 className="text-2xl font-bold tracking-tight text-text-primary">
                Ekip Yönetimi
              </h1>
              <p className="text-sm text-text-muted mt-0.5">
                Organizasyon üyelerini, erişim rollerini ve hesap durumlarını yönetin.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg border border-border bg-surface text-text-primary hover:bg-surface-elevated transition-colors disabled:opacity-50"
            title="Yenile"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            <span>Yenile</span>
          </button>

          {isAdmin && (
            <button
              onClick={() => {
                setAddError(null);
                setIsAddModalOpen(true);
              }}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-primary text-white hover:bg-primary-hover shadow-sm transition-colors"
            >
              <UserPlus size={16} />
              <span>Yeni Üye Ekle</span>
            </button>
          )}
        </div>
      </div>

      {/* ── Alert Banners ────────────────────────────────────────────────── */}
      {actionSuccess && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-700 dark:text-emerald-400 text-sm">
          <CheckCircle2 size={18} className="shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-700 dark:text-rose-400 text-sm">
          <AlertCircle size={18} className="shrink-0" />
          <div className="flex-1">
            <span className="font-medium">Hata: </span>
            {error}
          </div>
        </div>
      )}

      {!isAdmin && currentUser && (
        <div className="flex items-center gap-3 p-3.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-800 dark:text-amber-300 text-xs">
          <ShieldAlert size={16} className="shrink-0" />
          <span>
            Giriş yaptığınız rol: <strong>{ROLE_CONFIG[currentUser.role]?.label || currentUser.role}</strong>. 
            Üye ekleme, rol değiştirme ve pasife alma işlemleri yalnızca <strong>Yönetici (Admin)</strong> yetkisine açıktır.
          </span>
        </div>
      )}

      {/* ── KPI Stats Cards ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-xl border border-border bg-surface shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
              Toplam Üye
            </span>
            <Users size={18} className="text-text-muted" />
          </div>
          <div className="text-2xl font-bold text-text-primary mt-2">
            {totalCount}
          </div>
          <div className="text-xs text-text-muted mt-1">
            Organizasyonunuza kayıtlı tüm hesaplar
          </div>
        </div>

        <div className="p-5 rounded-xl border border-border bg-surface shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
              Aktif Üyeler
            </span>
            <UserCheck size={18} className="text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-2">
            {activeCount}
          </div>
          <div className="text-xs text-text-muted mt-1">
            Giriş yapabilen ve işlem yürüten hesaplar
          </div>
        </div>

        <div className="p-5 rounded-xl border border-border bg-surface shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
              Aktif Yöneticiler (Admin)
            </span>
            <Shield size={18} className="text-purple-600 dark:text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-purple-600 dark:text-purple-400 mt-2">
            {adminCount}
          </div>
          <div className="text-xs text-text-muted mt-1">
            {adminCount <= 1 ? "⚠️ Son aktif yönetici koruması devrede" : "Yönetim yetkisine sahip kullanıcılar"}
          </div>
        </div>
      </div>

      {/* ── Search & Filter Controls ─────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between bg-surface p-4 rounded-xl border border-border">
        <div className="relative flex-1 max-w-md">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="İsim veya e-posta ile ara..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
          />
        </div>

        <div className="flex items-center gap-3">
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            aria-label="Rol Filtresi"
            className="px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
          >
            <option value="all">Tüm Roller</option>
            <option value="admin">Yönetici (Admin)</option>
            <option value="manager">Satın Alma Yöneticisi</option>
            <option value="employee">Satın Alma Uzmanı</option>
            <option value="viewer">Gözlemci (Viewer)</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Durum Filtresi"
            className="px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
          >
            <option value="all">Tüm Durumlar</option>
            <option value="active">Yalnızca Aktif</option>
            <option value="inactive">Yalnızca Pasif</option>
          </select>
        </div>
      </div>

      {/* ── Team Table ──────────────────────────────────────────────────── */}
      <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-elevated/70 border-b border-border text-xs font-semibold text-text-muted uppercase tracking-wider">
              <tr>
                <th className="px-6 py-3.5">Üye</th>
                <th className="px-6 py-3.5">Rol</th>
                <th className="px-6 py-3.5">Durum</th>
                <th className="px-6 py-3.5">Kayıt Tarihi</th>
                <th className="px-6 py-3.5 text-right">İşlemler</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-text-muted">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <RefreshCw size={24} className="animate-spin text-primary" />
                      <span>Ekip üyeleri yükleniyor...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredMembers.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-text-muted">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <Users size={32} className="opacity-40" />
                      <p className="font-medium text-text-primary">Eşleşen üye bulunamadı</p>
                      <p className="text-xs">Arama kriterlerinizi değiştirmeyi deneyin.</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredMembers.map((member) => {
                  const isCurrentSessionUser = currentUser?.id === member.id;
                  const roleInfo = ROLE_CONFIG[member.role] || {
                    label: member.role,
                    desc: "",
                    badgeClass: "bg-gray-500/10 text-gray-500 border-gray-500/20",
                  };

                  return (
                    <tr 
                      key={member.id} 
                      className={`hover:bg-surface-elevated/50 transition-colors ${
                        !member.is_active ? "opacity-60 bg-surface-elevated/20" : ""
                      }`}
                    >
                      {/* Name & Email */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-full bg-primary/10 text-primary font-bold flex items-center justify-center text-sm shrink-0 border border-primary/20">
                            {member.full_name.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-text-primary">
                                {member.full_name}
                              </span>
                              {isCurrentSessionUser && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/20 text-primary font-semibold border border-primary/30">
                                  Siz
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-1.5 text-xs text-text-muted mt-0.5">
                              <Mail size={12} />
                              <span>{member.email}</span>
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Role */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <span 
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${roleInfo.badgeClass}`}
                            title={roleInfo.desc}
                          >
                            <Shield size={12} />
                            {roleInfo.label}
                          </span>
                        </div>
                      </td>

                      {/* Status */}
                      <td className="px-6 py-4">
                        {member.is_active ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                            Aktif
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-500/10 text-zinc-500 border border-zinc-500/20">
                            <span className="h-1.5 w-1.5 rounded-full bg-zinc-400"></span>
                            Pasif
                          </span>
                        )}
                      </td>

                      {/* Created At */}
                      <td className="px-6 py-4 text-xs text-text-muted">
                        {new Date(member.created_at).toLocaleDateString("tr-TR", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </td>

                      {/* Actions */}
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          
                          {/* Role Change Button (Admin only) */}
                          {isAdmin && (
                            <button
                              onClick={() => {
                                setModalActionError(null);
                                setRoleChangeMember(member);
                                setNewSelectedRole(member.role);
                              }}
                              className="px-2.5 py-1 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-elevated hover:bg-surface border border-border rounded-md transition-colors"
                              title="Rolü Değiştir"
                            >
                              Rol Değiştir
                            </button>
                          )}

                          {/* Deactivate / Reactivate Button */}
                          {isAdmin && (
                            <>
                              {member.is_active ? (
                                <button
                                  disabled={isCurrentSessionUser}
                                  onClick={() => {
                                    setModalActionError(null);
                                    setDeactivatingMember(member);
                                  }}
                                  className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors ${
                                    isCurrentSessionUser
                                      ? "opacity-40 cursor-not-allowed bg-zinc-500/10 text-zinc-400 border-zinc-500/20"
                                      : "text-rose-600 dark:text-rose-400 bg-rose-500/10 hover:bg-rose-500/20 border-rose-500/20"
                                  }`}
                                  title={
                                    isCurrentSessionUser
                                      ? "Kendi hesabınızı devre dışı bırakamazsınız."
                                      : "Kullanıcıyı pasife al"
                                  }
                                >
                                  Pasife Al
                                </button>
                              ) : (
                                <button
                                  onClick={() => {
                                    setModalActionError(null);
                                    setReactivatingMember(member);
                                  }}
                                  className="px-2.5 py-1 text-xs font-medium rounded-md border text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 border-emerald-500/20 transition-colors"
                                  title="Kullanıcıyı aktifleştir"
                                >
                                  Aktifleştir
                                </button>
                              )}
                            </>
                          )}

                          {!isAdmin && (
                            <span className="text-xs text-text-muted italic">Yetki yok</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Modal: Add New Member ────────────────────────────────────────── */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="bg-surface rounded-2xl border border-border shadow-xl max-w-md w-full overflow-hidden">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-primary/10 text-primary">
                  <UserPlus size={18} />
                </div>
                <div>
                  <h3 className="font-bold text-text-primary text-base">Yeni Ekip Üyesi Ekle</h3>
                  <p className="text-xs text-text-muted">Organizasyonunuza yeni bir çalışma arkadaşı tanımlayın</p>
                </div>
              </div>
              <button 
                onClick={() => setIsAddModalOpen(false)}
                className="text-text-muted hover:text-text-primary p-1 rounded-md"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleAddMember} className="p-5 space-y-4">
              {addError && (
                <div className="p-3 text-xs rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 flex items-center gap-2">
                  <AlertCircle size={14} className="shrink-0" />
                  <span>{addError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-text-primary mb-1">
                  Ad Soyad
                </label>
                <input
                  type="text"
                  required
                  placeholder="Örn: Ayşe Yılmaz"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-primary mb-1">
                  Kurumsal E-posta
                </label>
                <input
                  type="email"
                  required
                  placeholder="Örn: ayse@sirketiniz.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-primary mb-1">
                  Erişim Rolü
                </label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as UserRole)}
                  className="w-full px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
                >
                  <option value="employee">Satın Alma Uzmanı (Employee)</option>
                  <option value="manager">Satın Alma Yöneticisi (Manager)</option>
                  <option value="viewer">Gözlemci (Viewer)</option>
                  <option value="admin">Yönetici (Admin)</option>
                </select>
                <p className="text-[11px] text-text-muted mt-1">
                  {ROLE_CONFIG[role].desc}
                </p>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-text-primary">
                    Başlangıç Şifresi
                  </label>
                  <span className="text-[10px] text-text-muted">En az 8 karakter</span>
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    required
                    minLength={8}
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full pl-3 pr-10 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div className="pt-3 flex items-center justify-end gap-2 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-elevated border border-border rounded-lg transition-colors"
                >
                  Vazgeç
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-primary hover:bg-primary-hover rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  {isSubmitting && <RefreshCw size={14} className="animate-spin" />}
                  <span>{isSubmitting ? "Ekleniyor..." : "Üyeyi Kaydet"}</span>
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
                <h3 className="font-bold text-text-primary text-base">Rolü Güncelle</h3>
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
                Yeni Rol Seçin
              </label>
              <select
                value={newSelectedRole}
                onChange={(e) => setNewSelectedRole(e.target.value as UserRole)}
                className="w-full px-3 py-2 text-sm bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                <option value="admin">Yönetici (Admin)</option>
                <option value="manager">Satın Alma Yöneticisi (Manager)</option>
                <option value="employee">Satın Alma Uzmanı (Employee)</option>
                <option value="viewer">Gözlemci (Viewer)</option>
              </select>
              <p className="text-[11px] text-text-muted mt-1.5">
                {ROLE_CONFIG[newSelectedRole].desc}
              </p>
            </div>

            {roleChangeMember.role === "admin" && newSelectedRole !== "admin" && (
              <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-xs">
                ⚠️ Dikkat: Eğer bu kullanıcı organizasyondaki son aktif yönetici ise rolü düşürülemez.
              </div>
            )}

            <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
              <button
                onClick={() => setRoleChangeMember(null)}
                className="px-3.5 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-elevated border border-border rounded-lg"
              >
                Vazgeç
              </button>
              <button
                onClick={handleConfirmRoleChange}
                disabled={isSubmitting || newSelectedRole === roleChangeMember.role}
                className="px-3.5 py-1.5 text-xs font-semibold text-white bg-primary hover:bg-primary-hover rounded-lg disabled:opacity-50 flex items-center gap-1.5"
              >
                {isSubmitting && <RefreshCw size={14} className="animate-spin" />}
                <span>Güncelle</span>
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
                <h3 className="font-bold text-text-primary text-base">Üyeyi Pasife Al</h3>
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
              <strong>{deactivatingMember.full_name}</strong> kullanıcısının hesabı dondurulacaktır.
              Kullanıcı uygulamaya giriş yapamayacak ve API çağrıları reddedilecektir. İleride tekrar aktifleştirebilirsiniz.
            </p>

            {deactivatingMember.role === "admin" && (
              <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-xs">
                ⚠️ Güvenlik Değişmezi: Organizasyondaki son aktif yönetici pasife alınamaz.
              </div>
            )}

            <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
              <button
                onClick={() => setDeactivatingMember(null)}
                className="px-3.5 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-elevated border border-border rounded-lg"
              >
                Vazgeç
              </button>
              <button
                onClick={handleConfirmDeactivate}
                disabled={isSubmitting}
                className="px-3.5 py-1.5 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg disabled:opacity-50 flex items-center gap-1.5"
              >
                {isSubmitting && <RefreshCw size={14} className="animate-spin" />}
                <span>Pasife Al</span>
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
                <h3 className="font-bold text-text-primary text-base">Hesabı Aktifleştir</h3>
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
              <strong>{reactivatingMember.full_name}</strong> kullanıcısının hesabı yeniden etkinleştirilecektir.
              Kullanıcı mevcut bilgileriyle giriş yapabilir hale gelecektir.
            </p>

            <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
              <button
                onClick={() => setReactivatingMember(null)}
                className="px-3.5 py-1.5 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-elevated border border-border rounded-lg"
              >
                Vazgeç
              </button>
              <button
                onClick={handleConfirmReactivate}
                disabled={isSubmitting}
                className="px-3.5 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg disabled:opacity-50 flex items-center gap-1.5"
              >
                {isSubmitting && <RefreshCw size={14} className="animate-spin" />}
                <span>Aktifleştir</span>
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
