import React, { useState, useEffect } from "react";
import { fetchSystemStats, getHealthStatus } from "../services/api.js";
import { PanelError } from "./PanelStatus.jsx";

export default function DashboardModal({ isOpen, onClose }) {
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen) loadData();
  }, [isOpen]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, h] = await Promise.all([fetchSystemStats(), getHealthStatus()]);
      setStats(s);
      setHealth(h);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const StatusBadge = ({ value }) => {
    const ok = value && (value === "ONLINE" || value.startsWith("ok") || value === "configured");
    return (
      <span className={`flex items-center gap-1.5 text-xs font-medium ${ok ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
        <span className={`w-2 h-2 rounded-full ${ok ? "bg-emerald-500 animate-pulse" : "bg-rose-500"}`}></span>
        {ok ? "Online" : value || "Unknown"}
      </span>
    );
  };

  return (
    <div className="fixed inset-0 z-50 bg-charcoal-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-paper-100 dark:bg-charcoal-800 rounded-lg shadow-2xl border border-gold-500/30 w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-paper-300 dark:border-charcoal-700 bg-maroon-900 text-paper-100">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <h2 className="font-serif text-lg tracking-wide">Judiciary AI Live Dashboard</h2>
          </div>
          <button onClick={onClose} className="text-paper-100/70 hover:text-paper-100 text-lg">✕</button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {loading && (
            <div className="py-16 text-center text-charcoal-400 text-xs">Loading dashboard data...</div>
          )}

          {!loading && error && <PanelError message={error} onRetry={loadData} />}

          {!loading && !error && stats && (
            <>
              {/* Key Stats Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "Documents Indexed", value: stats.documents_indexed, icon: "📚" },
                  { label: "Total Chunks", value: stats.total_chunks, icon: "🔢" },
                  { label: "ChromaDB Chunks", value: stats.chroma_chunks, icon: "🗄️" },
                  { label: "Update Events", value: stats.total_updates, icon: "🔔" },
                ].map((s) => (
                  <div key={s.label} className="p-4 rounded border border-paper-300 dark:border-charcoal-700 bg-white dark:bg-charcoal-900/60 text-center">
                    <div className="text-2xl mb-1">{s.icon}</div>
                    <div className="text-2xl font-bold text-maroon-900 dark:text-gold-400 font-mono">{s.value ?? "—"}</div>
                    <div className="text-[11px] text-charcoal-500 dark:text-paper-300 mt-0.5">{s.label}</div>
                  </div>
                ))}
              </div>

              {/* Component Status Table */}
              <div className="p-4 rounded border border-paper-300 dark:border-charcoal-700 bg-white dark:bg-charcoal-900/60">
                <h3 className="font-serif text-sm font-bold text-charcoal-800 dark:text-paper-100 mb-3 uppercase tracking-wider">
                  Component Status
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                  {[
                    { label: "System API", value: "ONLINE" },
                    { label: "Vector Search (ChromaDB)", value: stats.vector_search },
                    { label: "BM25 Keyword Search", value: stats.bm25_search },
                    { label: "Result Reranker", value: stats.reranker },
                    { label: "LLM Provider", value: health?.llm_provider === "groq" ? "Groq (Fast)" : `Ollama (${health?.llm_model || "local"})` },
                    { label: "Document Monitor", value: stats.document_monitor },
                    { label: "MongoDB", value: health?.mongodb === "ok" ? "ONLINE" : health?.mongodb },
                    { label: "Knowledge Graph", value: health?.knowledge_graph ? "ONLINE" : "offline" },
                    { label: "FAISS Index", value: health?.faiss_index === "ok" ? "ONLINE" : health?.faiss_index },
                  ].map((item) => (
                    <div key={item.label} className="flex items-center justify-between p-2.5 rounded bg-paper-100 dark:bg-charcoal-800 border border-paper-200 dark:border-charcoal-700">
                      <span className="text-charcoal-600 dark:text-paper-300 text-[11px]">{item.label}</span>
                      <StatusBadge value={item.value} />
                    </div>
                  ))}
                </div>
              </div>

              {/* Knowledge Graph Stats */}
              {health?.knowledge_graph && (
                <div className="p-4 rounded border border-paper-300 dark:border-charcoal-700 bg-white dark:bg-charcoal-900/60">
                  <h3 className="font-serif text-sm font-bold text-charcoal-800 dark:text-paper-100 mb-1 uppercase tracking-wider">
                    Knowledge Graph
                  </h3>
                  <p className="text-sm text-charcoal-700 dark:text-paper-200 font-mono">{health.knowledge_graph}</p>
                  <p className="text-[11px] text-charcoal-400 mt-1">
                    Pre-compiled constitutional provisions, amendments, writ relationships, and concept linkages.
                  </p>
                </div>
              )}

              {/* Legal Disclaimer */}
              <div className="text-[11px] text-charcoal-500 dark:text-paper-400 border border-paper-300 dark:border-charcoal-700 rounded p-3 bg-paper-200/50 dark:bg-charcoal-900/40">
                ⚖️ <strong>Notice:</strong> This system provides information based on indexed legal documents and is not a substitute for professional legal advice. Always consult a qualified advocate for actionable legal guidance.
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
