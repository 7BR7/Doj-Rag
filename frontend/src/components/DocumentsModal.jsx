import React, { useState, useEffect } from "react";
import { fetchDocuments } from "../services/api.js";
import { PanelEmpty, PanelError } from "./PanelStatus.jsx";

export default function DocumentsModal({ isOpen, onClose, onAskAboutDoc }) {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadDocs();
    }
  }, [isOpen]);

  const loadDocs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDocuments();
      setDocs(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-charcoal-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-paper-100 dark:bg-charcoal-800 rounded-lg shadow-2xl border border-gold-500/30 w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-paper-300 dark:border-charcoal-700 bg-maroon-900 text-paper-100">
          <div className="flex items-center gap-2">
            <span className="text-gold-400 font-serif text-lg">📚</span>
            <h2 className="font-serif text-lg tracking-wide">Indexed Judiciary Document Repository</h2>
          </div>
          <button onClick={onClose} className="text-paper-100/70 hover:text-paper-100 text-lg">
            ✕
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          {loading && (
            <div className="col-span-2 py-16 text-center text-charcoal-400 text-xs">Loading legal documents...</div>
          )}

          {!loading && error && <div className="col-span-2"><PanelError message={error} onRetry={loadDocs} /></div>}
          {!loading && !error && docs.length === 0 && (
            <div className="col-span-2"><PanelEmpty>No documents are indexed yet. Process the PDFs and retry.</PanelEmpty></div>
          )}

          {!loading && !error && docs.map((d) => (
            <div
              key={d.document_id}
              className="p-3.5 rounded border border-paper-300 dark:border-charcoal-700 bg-white dark:bg-charcoal-900/60 space-y-2 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-maroon-800 dark:text-gold-400 line-clamp-1">
                    {d.document_name}
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-paper-200 dark:bg-charcoal-800 text-charcoal-600 dark:text-paper-300">
                    {d.document_type || "Bare Act"}
                  </span>
                </div>
                <div className="flex gap-4 text-[11px] text-charcoal-500 mt-1">
                  <span>Sections/Units: {d.num_units || 0}</span>
                  <span>Chunks: {d.num_chunks || 0}</span>
                </div>
              </div>

              <div className="pt-2 border-t border-paper-200 dark:border-charcoal-700 flex justify-between items-center text-xs">
                <span className="text-[10px] text-emerald-600 dark:text-emerald-400">● Indexed & Verified</span>
                <button
                  onClick={() => {
                    if (onAskAboutDoc) {
                      onAskAboutDoc(d);
                      onClose();
                    }
                  }}
                  className="px-2.5 py-1 text-[11px] font-medium rounded bg-maroon-800 hover:bg-maroon-700 text-gold-200 transition-colors"
                >
                  Ask About This Document →
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
