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
  ExternalLink,
  BookOpen,
  Layers,
  ChevronDown,
  ChevronUp,
  Sparkles
} from "lucide-react";
import { policiesApi, PolicyDocument, PolicySearchResponse } from "@/lib/api/policies";

const DOC_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  procurement_policy: { label: "Satın Alma Politikası", color: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
  sla: { label: "Hizmet Seviyesi (SLA)", color: "bg-purple-500/10 text-purple-500 border-purple-500/20" },
  code_of_conduct: { label: "Davranış Kuralları", color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" },
  framework_agreement: { label: "Çerçeve Sözleşme", color: "bg-amber-500/10 text-amber-500 border-amber-500/20" },
  legal: { label: "Yasal Kural", color: "bg-rose-500/10 text-rose-500 border-rose-500/20" },
  other: { label: "Diğer Belge", color: "bg-gray-500/10 text-text-muted border-gray-500/20" },
};

function formatPolicyText(rawText: string) {
  const lines = rawText.split("\n");
  return lines.map((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) return <div key={idx} className="h-1.5" />;

    // Skip redundant top markdown title if it's identical to header
    if (trimmed.startsWith("# ") || trimmed.startsWith("---")) {
      return null;
    }

    const isSubItem = /^\d+\.\d+\.?/.test(trimmed) || trimmed.startsWith("- ") || trimmed.startsWith("* ");
    const parts = trimmed.split(/(\*\*[^*]+\*\*)/g);

    return (
      <div 
        key={idx} 
        className={`leading-relaxed text-xs ${
          isSubItem 
            ? "pl-2.5 text-text-primary border-l-2 border-primary/30 my-1 py-0.5 bg-surface/50 rounded-r" 
            : "text-text-secondary my-0.5"
        }`}
      >
        {parts.map((part, pIdx) => {
          if (part.startsWith("**") && part.endsWith("**")) {
            return (
              <strong key={pIdx} className="font-semibold text-text-primary">
                {part.slice(2, -2)}
              </strong>
            );
          }
          const cleanPart = part.replace(/^#{1,3}\s+/, "").replace(/&#x20;/g, " ");
          return <span key={pIdx}>{cleanPart}</span>;
        })}
      </div>
    );
  });
}

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
  const [isContextExpanded, setIsContextExpanded] = useState(false);

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
                      <div className="flex items-center justify-end gap-1.5">
                        <a
                          href={policiesApi.getFileUrl(policy.id)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1.5 text-text-muted hover:text-primary hover:bg-surface-elevated rounded transition-colors"
                          title="Orijinal Belgeyi Aç (PDF)"
                        >
                          <ExternalLink size={16} />
                        </a>
                        <button
                          onClick={() => handleDelete(policy.id, policy.title)}
                          className="p-1.5 text-text-muted hover:text-red-500 hover:bg-red-500/10 rounded transition-colors"
                          title="Belgeyi ve vektörleri sil"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
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
          <div className="mt-6 flex flex-col gap-6">
            {/* Çoklu Belge Kapsamı Bildirimi */}
            {(() => {
              const uniqueTitles = Array.from(new Set(searchResult.hits.map(h => h.title || h.source)));
              if (uniqueTitles.length > 1) {
                return (
                  <div className="p-3.5 bg-blue-500/10 border border-blue-500/20 rounded-lg flex items-start gap-3">
                    <Sparkles className="text-blue-500 h-5 w-5 shrink-0 mt-0.5" />
                    <div className="text-xs">
                      <strong className="text-text-primary block font-semibold mb-0.5">
                        Çoklu Belge Kapsamı ({uniqueTitles.length} Farklı Kaynak Belge)
                      </strong>
                      <span className="text-text-secondary leading-relaxed">
                        Bu sorgu için hem <strong>{uniqueTitles.join("</strong> hem de <strong>")}</strong> belgelerinden ilgili hükümler getirildi. Olası çelişkiler veya tamamlayıcı maddeler aşağıda kaynak kartlarında bağımsız olarak gösterilmektedir.
                      </span>
                    </div>
                  </div>
                );
              }
              return null;
            })()}

            {/* Kaynak Kartları (Source Cards) */}
            {searchResult.hits.length > 0 ? (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                    Eşleşen Kaynak Kartları ({searchResult.hits.length} Parça)
                  </span>
                  <span className="text-xs text-text-muted hidden sm:inline">
                    Doğrudan ilgili madde hükümleri önceliklendirilmiştir
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {searchResult.hits.map((hit, idx) => {
                    const docType = hit.document_type || "other";
                    const docConfig = DOC_TYPE_CONFIG[docType] || DOC_TYPE_CONFIG.other;
                    const fileUrl = hit.doc_id ? policiesApi.getFileUrl(hit.doc_id, hit.page_number) : null;

                    return (
                      <div 
                        key={idx} 
                        className="bg-surface-elevated border border-border rounded-lg p-4 flex flex-col justify-between hover:border-primary/40 transition-colors shadow-sm"
                      >
                        <div>
                          {/* Kart Başlığı ve Meta Veriler */}
                          <div className="flex items-start justify-between gap-2 mb-2 pb-2.5 border-b border-border/50">
                            <div className="flex flex-col gap-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded border ${docConfig.color}`}>
                                  {docConfig.label}
                                </span>
                                {hit.page_number && (
                                  <span className="text-[10px] bg-bg px-2 py-0.5 rounded border border-border text-text-muted flex items-center gap-1 font-medium">
                                    <BookOpen size={11} className="text-primary" /> Sayfa {hit.page_number}
                                  </span>
                                )}
                                <span className="text-[10px] bg-bg px-2 py-0.5 rounded border border-border text-text-muted font-mono">
                                  #{hit.chunk_index + 1}
                                </span>
                              </div>
                              <h4 className="font-semibold text-text-primary text-xs truncate mt-0.5" title={hit.title || hit.source}>
                                {hit.title || hit.source}
                              </h4>
                            </div>

                            {/* Orijinal Belgeyi Aç Butonu */}
                            {fileUrl ? (
                              <a
                                href={fileUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="shrink-0 flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-primary bg-primary/10 hover:bg-primary/20 rounded transition-colors"
                                title="Orijinal PDF belgesini ilgili sayfada aç"
                              >
                                <ExternalLink size={12} />
                                <span>Aç</span>
                              </a>
                            ) : (
                              <span className="text-[10px] text-text-muted italic">Bağlantı yok</span>
                            )}
                          </div>

                          {/* Madde / Bölüm Başlığı */}
                          {hit.section_title && (
                            <div className="text-xs font-semibold text-primary mb-2 flex items-center gap-1.5 bg-primary/5 px-2.5 py-1.5 rounded border border-primary/15">
                              <Layers size={13} className="shrink-0 text-primary" />
                              <span className="truncate">{hit.section_title}</span>
                            </div>
                          )}

                          {/* Okunabilir Formatlanmış Metin */}
                          <div className="mt-2 text-xs">
                            {formatPolicyText(hit.text)}
                          </div>
                        </div>

                        {/* Kart Alt Bilgisi */}
                        <div className="mt-3 pt-2.5 border-t border-border/50 flex items-center justify-between text-[11px] text-text-muted">
                          <span className="truncate max-w-[170px]" title={hit.file_name || ""}>
                            📄 {hit.file_name || "Belge"}
                          </span>
                          {hit.score !== undefined && hit.score !== null && (
                            <span className="text-[10px] font-mono bg-bg px-1.5 py-0.5 rounded text-text-secondary border border-border">
                              Skor: {hit.score.toFixed(3)}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="p-4 bg-bg border border-border rounded-md text-xs text-text-muted text-center">
                Bu sorgu için eşleşen politika parçası bulunamadı.
              </div>
            )}

            {/* Katlanabilir LLM Bağlamı (Raw Context) */}
            <div className="border border-border rounded-lg overflow-hidden bg-bg">
              <button
                type="button"
                onClick={() => setIsContextExpanded(!isContextExpanded)}
                className="w-full flex items-center justify-between p-3.5 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-surface/50 transition-colors"
              >
                <span className="flex items-center gap-2">
                  <span className="font-semibold text-text-muted uppercase tracking-wider">
                    LLM&apos;e İletilen Bağlam (Context)
                  </span>
                  <span className="text-[11px] text-text-muted">
                    ({searchResult.hits.length} kaynak birleştirildi)
                  </span>
                </span>
                {isContextExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
              </button>

              {isContextExpanded && (
                <div className="p-4 border-t border-border bg-bg/80">
                  <pre className="text-xs text-text-primary font-mono whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
                    {searchResult.context}
                  </pre>
                </div>
              )}
            </div>
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
