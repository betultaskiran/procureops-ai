"use client";

import React, { useState, useEffect } from "react";
import { 
  ShieldCheck, 
  Upload, 
  FileText, 
  Trash2, 
  Search, 
  CheckCircle2, 
  AlertCircle, 
  Clock, 
  RefreshCw,
  HelpCircle,
  FileSearch,
  ExternalLink
} from "lucide-react";
import { policiesApi, PolicyDocument, PolicySearchResponse } from "@/lib/api/policies";

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<PolicyDocument[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Upload modal state
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDocType, setUploadDocType] = useState("procurement_policy");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // RAG Search test state
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<PolicySearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Fetch policies
  const loadPolicies = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await policiesApi.listPolicies();
      setPolicies(data);
    } catch (err: any) {
      setError(err.message || "Politika belgeleri yüklenemedi.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadPolicies();
  }, []);

  // Handle Upload
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadError("Lütfen bir dosya seçin.");
      return;
    }
    if (!uploadTitle.trim()) {
      setUploadError("Lütfen belge başlığını girin.");
      return;
    }

    try {
      setIsUploading(true);
      setUploadError(null);

      const formData = new FormData();
      formData.append("file", uploadFile);
      formData.append("title", uploadTitle.trim());
      formData.append("document_type", uploadDocType);

      await policiesApi.uploadPolicy(formData);

      // Reset form & reload
      setUploadTitle("");
      setUploadFile(null);
      setIsUploadOpen(false);
      await loadPolicies();
    } catch (err: any) {
      setUploadError(err.message || "Belge yüklenirken bir hata oluştu.");
    } finally {
      setIsUploading(false);
    }
  };

  // Handle Delete
  const handleDelete = async (id: string, title: string) => {
    if (!confirm(`"${title}" belgesini ve vektör veritabanındaki tüm embedding'lerini silmek istediğinize emin misiniz?`)) {
      return;
    }

    try {
      await policiesApi.deletePolicy(id);
      await loadPolicies();
      if (searchResult) {
        setSearchResult(null);
      }
    } catch (err: any) {
      alert(`Silme başarısız: ${err.message}`);
    }
  };

  // Handle RAG Search Test
  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    try {
      setIsSearching(true);
      setSearchError(null);
      const res = await policiesApi.testSearch(searchQuery.trim(), 3);
      setSearchResult(res);
    } catch (err: any) {
      setSearchError(err.message || "RAG araması başarısız oldu.");
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="flex flex-col gap-8 pb-12">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="text-primary h-7 w-7" />
            <h1 className="text-2xl font-bold tracking-tight text-text-primary">
              Company Policies & Knowledge Base
            </h1>
          </div>
          <p className="text-sm text-text-muted mt-1">
            RAG (Retrieval-Augmented Generation) hafızası: Politika belgeleri Qdrant vektör tabanında saklanır ve analiz sırasında kanıt olarak kullanılır.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadPolicies()}
            className="p-2 text-text-muted hover:text-text-primary hover:bg-surface-elevated rounded-md border border-border transition-colors"
            title="Yenile"
          >
            <RefreshCw size={18} className={isLoading ? "animate-spin" : ""} />
          </button>

          <button
            onClick={() => setIsUploadOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-md text-sm font-medium transition-colors shadow-sm"
          >
            <Upload size={16} />
            Upload Policy
          </button>
        </div>
      </div>

      {/* ── Architecture Note Card ─────────────────────────────────────── */}
      <div className="bg-surface border border-border rounded-lg p-5">
        <div className="flex items-start gap-3">
          <div className="p-2 bg-primary/10 rounded-md text-primary mt-0.5">
            <HelpCircle size={18} />
          </div>
          <div className="text-sm text-text-secondary leading-relaxed space-y-1">
            <p className="font-semibold text-text-primary">RAG ve Deterministik Kural Mimarisi</p>
            <p>
              • <strong>Deterministik Kontroller:</strong> Bütçe limitleri, maksimum teslimat günleri ve asgari garanti süreleri LLM halüsinasyonuna bırakılmaz; backend kural motoru tarafından matematiksel olarak denetlenir.
            </p>
            <p>
              • <strong>RAG & Kanıt Çıkarımı:</strong> Yüklenen belgeler Qdrant&apos;ta parçalara (chunks) bölünür. Analiz esnasında ilgili maddeler bulunur, kaynak atıfları ile <code>[Kaynak X: Belge Adı]</code> şeklinde karar gerekçesine kanıt olarak işlenir.
            </p>
          </div>
        </div>
      </div>

      {/* ── Policies List Table ─────────────────────────────────────────── */}
      <div className="bg-surface border border-border rounded-lg shadow-sm overflow-hidden">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText size={18} className="text-text-muted" />
            <h2 className="font-semibold text-text-primary text-base">Aktif Şirket Politikaları</h2>
            <span className="text-xs px-2 py-0.5 rounded-full bg-surface-elevated border border-border text-text-muted font-medium">
              {policies.length}
            </span>
          </div>
        </div>

        {isLoading ? (
          <div className="p-12 text-center text-text-muted flex flex-col items-center gap-3">
            <RefreshCw size={24} className="animate-spin text-primary" />
            <span>Politika belgeleri yükleniyor...</span>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-red-500 flex flex-col items-center gap-2">
            <AlertCircle size={24} />
            <span>{error}</span>
          </div>
        ) : policies.length === 0 ? (
          <div className="p-12 text-center text-text-muted flex flex-col items-center gap-3">
            <FileText size={32} className="opacity-40" />
            <p className="font-medium text-text-primary">Henüz politika belgesi yüklenmedi</p>
            <p className="text-xs max-w-sm">
              Tedarikçi tekliflerini değerlendirirken kullanılacak satın alma yönergelerini, SLA veya sertifika şartlarını PDF/TXT olarak yükleyebilirsiniz.
            </p>
            <button
              onClick={() => setIsUploadOpen(true)}
              className="mt-2 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary rounded-md text-xs font-medium transition-colors"
            >
              İlk Belgeyi Yükle
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-elevated/50 text-text-muted text-xs border-b border-border">
                <tr>
                  <th className="py-3 px-4 font-medium">Belge Adı</th>
                  <th className="py-3 px-4 font-medium">Tür</th>
                  <th className="py-3 px-4 font-medium">Dosya</th>
                  <th className="py-3 px-4 font-medium">RAG / Vektör Durumu</th>
                  <th className="py-3 px-4 font-medium">Yüklenme Tarihi</th>
                  <th className="py-3 px-4 font-medium text-right">İşlemler</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {policies.map((policy) => (
                  <tr key={policy.id} className="hover:bg-surface-elevated/30 transition-colors">
                    <td className="py-3.5 px-4 font-medium text-text-primary">
                      {policy.title}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-block px-2 py-0.5 text-xs rounded bg-surface-elevated border border-border text-text-secondary capitalize">
                        {policy.document_type.replace("_", " ")}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-text-muted text-xs">
                      {policy.file_name}
                    </td>
                    <td className="py-3.5 px-4">
                      {policy.is_chunked ? (
                        <div className="flex items-center gap-1.5 text-emerald-500 text-xs font-medium">
                          <CheckCircle2 size={15} />
                          <span>Qdrant Hazır ({policy.chunk_count || 1} parça)</span>
                        </div>
                      ) : policy.processing_error ? (
                        <div className="flex items-center gap-1.5 text-red-500 text-xs font-medium" title={policy.processing_error}>
                          <AlertCircle size={15} />
                          <span className="truncate max-w-[200px]">Hata: {policy.processing_error}</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-amber-500 text-xs font-medium">
                          <Clock size={15} />
                          <span>İşleniyor...</span>
                        </div>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-text-muted text-xs">
                      {policy.created_at ? new Date(policy.created_at).toLocaleDateString("tr-TR") : "-"}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => handleDelete(policy.id, policy.title)}
                        className="p-1.5 text-text-muted hover:text-red-500 hover:bg-red-500/10 rounded transition-colors"
                        title="Belgeyi ve vektörleri sil"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Interactive RAG Retrieval Tester ───────────────────────────── */}
      <div className="bg-surface border border-border rounded-lg shadow-sm p-6">
        <div className="flex items-center gap-2 mb-2">
          <FileSearch className="text-primary h-5 w-5" />
          <h2 className="font-semibold text-text-primary text-base">RAG Semantik Arama Test Konsolu</h2>
        </div>
        <p className="text-xs text-text-muted mb-4">
          Qdrant Hybrid Search (Dense Gemini + Sparse BM25) doğrulaması. Sorulan soruya karşılık gelen politika parçalarını ve kaynak atıflarını doğrudan test edin.
        </p>

        <form onSubmit={handleSearch} className="flex gap-2 mb-4">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Örn: ISO 9001 sertifikası şartı nedir? veya Maksimum ödeme vadesi kaç gün?"
            className="flex-1 px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary"
          />
          <button
            type="submit"
            disabled={isSearching || !searchQuery.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white rounded-md text-sm font-medium transition-colors"
          >
            <Search size={16} />
            {isSearching ? "Aranıyor..." : "Sorgula"}
          </button>
        </form>

        {searchError && (
          <div className="p-3 text-sm text-red-500 bg-red-500/10 border border-red-500/20 rounded-md">
            {searchError}
          </div>
        )}

        {searchResult && (
          <div className="mt-4 flex flex-col gap-4">
            <div className="p-4 bg-bg border border-border rounded-md">
              <span className="text-xs font-semibold text-text-muted uppercase tracking-wider block mb-2">
                LLM&apos;e İletilen Bağlam (Context):
              </span>
              <pre className="text-xs text-text-primary font-mono whitespace-pre-wrap leading-relaxed">
                {searchResult.context}
              </pre>
            </div>

            {searchResult.hits.length > 0 && (
              <div>
                <span className="text-xs font-semibold text-text-muted uppercase tracking-wider block mb-2">
                  Eşleşen Vektör Parçaları ({searchResult.hits.length}):
                </span>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {searchResult.hits.map((hit, idx) => (
                    <div key={idx} className="p-3 bg-surface-elevated border border-border rounded-md flex flex-col justify-between">
                      <div>
                        <div className="text-xs font-medium text-primary mb-1">
                          {hit.source} (Parça #{hit.chunk_index + 1})
                        </div>
                        <p className="text-xs text-text-secondary line-clamp-4 leading-relaxed">
                          {hit.text}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Upload Modal ────────────────────────────────────────────────── */}
      {isUploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-surface border border-border rounded-lg shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4 border-b border-border pb-3">
              <h3 className="font-semibold text-text-primary text-lg">Politika Belgesi Yükle</h3>
              <button 
                onClick={() => setIsUploadOpen(false)}
                className="text-text-muted hover:text-text-primary text-xl font-bold leading-none"
              >
                &times;
              </button>
            </div>

            {uploadError && (
              <div className="p-3 mb-4 text-xs text-red-500 bg-red-500/10 border border-red-500/20 rounded-md">
                {uploadError}
              </div>
            )}

            <form onSubmit={handleUploadSubmit} className="flex flex-col gap-4">
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">
                  Belge Başlığı *
                </label>
                <input
                  type="text"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  placeholder="Örn: 2026 Donanım Satın Alma ve Kalite Politikası"
                  className="w-full px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">
                  Belge Türü
                </label>
                <select
                  value={uploadDocType}
                  onChange={(e) => setUploadDocType(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-bg border border-border rounded-md text-text-primary focus:outline-none focus:border-primary"
                >
                  <option value="procurement_policy">Satın Alma Politikası (Procurement Policy)</option>
                  <option value="sla">Hizmet Seviyesi Taahhüdü (SLA)</option>
                  <option value="code_of_conduct">Tedarikçi Davranış Kuralları</option>
                  <option value="framework_agreement">Çerçeve Sözleşme</option>
                  <option value="legal">Yasal / Regülasyon Kuralı</option>
                  <option value="other">Diğer</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">
                  Dosya (PDF, TXT, MD) *
                </label>
                <input
                  type="file"
                  accept=".pdf,.txt,.md"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-text-secondary file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-surface-elevated file:text-text-primary hover:file:bg-border cursor-pointer"
                  required
                />
                <p className="text-[11px] text-text-muted mt-1">
                  Maksimum dosya boyutu 20 MB. PDF, metin veya markdown dosyaları.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 mt-4 pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsUploadOpen(false)}
                  className="px-4 py-2 border border-border text-text-secondary hover:text-text-primary rounded-md text-sm font-medium transition-colors"
                >
                  İptal
                </button>
                <button
                  type="submit"
                  disabled={isUploading}
                  className="px-4 py-2 bg-primary hover:bg-primary-hover disabled:opacity-50 text-white rounded-md text-sm font-medium transition-colors flex items-center gap-2"
                >
                  {isUploading ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      İşleniyor (Chunking & Vektör)...
                    </>
                  ) : (
                    "Yükle ve İndeksle"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
