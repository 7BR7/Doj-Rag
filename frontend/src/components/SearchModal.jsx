import React, { useState } from "react";
import { searchLegalDocuments } from "../services/api.js";
import { PanelError } from "./PanelStatus.jsx";

export default function SearchModal({ isOpen, onClose, onSelectResult }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const runSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    setError(null);
    try {
      const data = await searchLegalDocuments(query);
      setResults(data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    runSearch();
  };

  return (
    <div className="fixed inset-0 z-50 bg-charcoal-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-paper-100 dark:bg-charcoal-800 rounded-lg shadow-2xl border border-gold-500/30 w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-paper-300 dark:border-charcoal-700 bg-maroon-900 text-paper-100">
          <div className="flex items-center gap-2">
            <span className="text-gold-400 font-serif text-lg">🔍</span>
            <h2 className="font-serif text-lg tracking-wide">Legal Document Search</h2>
          </div>
          <button onClick={onClose} className="text-paper-100/70 hover:text-paper-100 text-lg">
            ✕
          </button>
        </div>

        {/* Input Bar */}
        <form onSubmit={handleSearch} className="p-4 border-b border-paper-300 dark:border-charcoal-700 flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search Acts, Sections (e.g. Section 12), Articles, keywords..."
            className="flex-1 px-4 py-2 text-sm rounded border border-paper-300 dark:border-charcoal-600 bg-white dark:bg-charcoal-900 text-charcoal-900 dark:text-paper-100 focus:outline-none focus:ring-1 focus:ring-gold-500"
            autoFocus
          />
          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2 text-sm font-medium rounded bg-maroon-800 hover:bg-maroon-700 text-gold-300 transition-colors"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        {/* Results */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading && (
            <div className="py-12 text-center text-charcoal-400 text-sm">
              Searching indexed legal documents & vector stores...
            </div>
          )}

          {!loading && error && <PanelError message={error} onRetry={runSearch} />}

          {!loading && !error && searched && results.length === 0 && (
            <div className="py-12 text-center text-charcoal-500 text-sm">
              No matching sections or legal provisions found for "{query}".
            </div>
          )}

          {!loading && !error && results.map((r) => (
            <div
              key={r.chunk_id}
              className="p-3.5 rounded border border-paper-300 dark:border-charcoal-700 hover:border-gold-500/50 bg-white dark:bg-charcoal-900/60 transition-all cursor-pointer group"
              onClick={() => {
                if (onSelectResult) {
                  onSelectResult(r);
                  onClose();
                }
              }}
            >
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="font-semibold text-maroon-800 dark:text-gold-400">
                  {r.document_name}
                </span>
                <span className="text-charcoal-400">
                  {r.section ? `Section ${r.section}` : r.article ? `Article ${r.article}` : `Page ${r.page_start}`}
                </span>
              </div>
              <p className="text-xs text-charcoal-700 dark:text-paper-200 line-clamp-3 leading-relaxed">
                {r.snippet}
              </p>
              <div className="mt-2 flex items-center justify-between text-[11px] text-gold-600 dark:text-gold-400/80">
                <span>Click to ask chatbot about this provision →</span>
                <span>Page {r.page_start}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
