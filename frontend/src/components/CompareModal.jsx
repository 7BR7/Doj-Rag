import React, { useState, useEffect } from "react";
import { compareVersions } from "../services/api.js";
import { PanelError } from "./PanelStatus.jsx";

export default function CompareModal({ isOpen, onClose }) {
  const [docId, setDocId] = useState("bns");
  const [verA, setVerA] = useState("1.0");
  const [verB, setVerB] = useState("2.0");
  const [section, setSection] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const runCompare = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await compareVersions(docId, verA, verB, section);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = (e) => {
    e.preventDefault();
    runCompare();
  };

  return (
    <div className="fixed inset-0 z-50 bg-charcoal-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-paper-100 dark:bg-charcoal-800 rounded-lg shadow-2xl border border-gold-500/30 w-full max-w-4xl max-h-[88vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-paper-300 dark:border-charcoal-700 bg-maroon-900 text-paper-100">
          <div className="flex items-center gap-2">
            <span className="text-gold-400 font-serif text-lg">⚖️</span>
            <h2 className="font-serif text-lg tracking-wide">Legal Document Change Detection ("What Changed?")</h2>
          </div>
          <button onClick={onClose} className="text-paper-100/70 hover:text-paper-100 text-lg">
            ✕
          </button>
        </div>

        {/* Filter Controls */}
        <form onSubmit={handleCompare} className="p-4 border-b border-paper-300 dark:border-charcoal-700 grid grid-cols-4 gap-3 bg-paper-200/50 dark:bg-charcoal-900/40">
          <div>
            <label className="block text-[11px] font-semibold text-charcoal-600 dark:text-paper-300 uppercase mb-1">Document</label>
            <select
              value={docId}
              onChange={(e) => setDocId(e.target.value)}
              className="w-full text-xs p-2 rounded border border-paper-300 dark:border-charcoal-600 bg-white dark:bg-charcoal-900"
            >
              <option value="bns">Bharatiya Nyaya Sanhita (BNS)</option>
              <option value="bnss">Bharatiya Nagarik Suraksha Sanhita (BNSS)</option>
              <option value="bsa">Bharatiya Sakshya Adhiniyam (BSA)</option>
              <option value="constitution">Constitution of India</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-charcoal-600 dark:text-paper-300 uppercase mb-1">Baseline Version</label>
            <input
              type="text"
              value={verA}
              onChange={(e) => setVerA(e.target.value)}
              className="w-full text-xs p-2 rounded border border-paper-300 dark:border-charcoal-600 bg-white dark:bg-charcoal-900"
            />
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-charcoal-600 dark:text-paper-300 uppercase mb-1">Amended Version</label>
            <input
              type="text"
              value={verB}
              onChange={(e) => setVerB(e.target.value)}
              className="w-full text-xs p-2 rounded border border-paper-300 dark:border-charcoal-600 bg-white dark:bg-charcoal-900"
            />
          </div>

          <div className="flex items-end gap-2">
            <div className="flex-1">
              <label className="block text-[11px] font-semibold text-charcoal-600 dark:text-paper-300 uppercase mb-1">Section (Optional)</label>
              <input
                type="text"
                value={section}
                onChange={(e) => setSection(e.target.value)}
                placeholder="e.g. 12"
                className="w-full text-xs p-2 rounded border border-paper-300 dark:border-charcoal-600 bg-white dark:bg-charcoal-900"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 text-xs font-semibold rounded bg-maroon-800 hover:bg-maroon-700 text-gold-200 transition-colors"
            >
              {loading ? "Diffing..." : "Compare"}
            </button>
          </div>
        </form>

        {/* Diff View */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 font-mono text-xs">
          {!result && !loading && (
            <div className="py-16 text-center text-charcoal-500 font-sans text-sm">
              Select versions and click Compare to inspect added clauses, modified provisions, and unified legal diffs.
            </div>
          )}

          {loading && (
            <div className="py-16 text-center text-charcoal-500 font-sans text-sm">
              Computing diff across legal versions...
            </div>
          )}

          {!loading && error && <PanelError message={error} onRetry={runCompare} />}

          {result && !error && (
            <div>
              <div className="flex gap-4 mb-3 text-xs font-sans">
                <span className="px-2.5 py-1 rounded bg-emerald-100 text-emerald-800 font-medium">
                  + Added clauses: {result.added_count || 0}
                </span>
                <span className="px-2.5 py-1 rounded bg-rose-100 text-rose-800 font-medium">
                  - Removed clauses: {result.removed_count || 0}
                </span>
              </div>

              {result.unified_diff ? (
                <pre className="p-4 rounded bg-charcoal-950 text-paper-100 overflow-x-auto leading-relaxed border border-charcoal-700 whitespace-pre-wrap">
                  {result.unified_diff}
                </pre>
              ) : (
                <div className="p-4 rounded bg-paper-200 dark:bg-charcoal-900 text-charcoal-600 dark:text-paper-300 font-sans text-xs">
                  No textual differences between Version {verA} and Version {verB} for the selected parameters. Both versions align.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
