import React, { useState, useEffect } from "react";
import { fetchTimeline } from "../services/api.js";
import { PanelEmpty, PanelError } from "./PanelStatus.jsx";

export default function TimelineModal({ isOpen, onClose }) {
  const [timeline, setTimeline] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadTimeline();
    }
  }, [isOpen]);

  const loadTimeline = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTimeline();
      setTimeline(data || []);
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
            <span className="text-gold-400 font-serif text-lg">⏳</span>
            <h2 className="font-serif text-lg tracking-wide">Legal Document Timeline & Legislative History</h2>
          </div>
          <button onClick={onClose} className="text-paper-100/70 hover:text-paper-100 text-lg">
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading && (
            <div className="py-16 text-center text-charcoal-400 text-xs">Loading legal timeline...</div>
          )}

          {!loading && error && <PanelError message={error} onRetry={loadTimeline} />}

          {!loading && !error && timeline.length === 0 && (
            <PanelEmpty>No timeline entries are available yet.</PanelEmpty>
          )}

          {!loading && !error && timeline.length > 0 && (
            <div className="relative border-l-2 border-gold-500/40 ml-4 space-y-6">
              {timeline.map((item, idx) => (
                <div key={item.version_id || idx} className="relative pl-6">
                  {/* Pin */}
                  <div className="absolute -left-[9px] top-1 w-4 h-4 rounded-full bg-maroon-900 border-2 border-gold-400"></div>

                  <div className="p-3.5 rounded border border-paper-300 dark:border-charcoal-700 bg-white dark:bg-charcoal-900/60 space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-maroon-800 dark:text-gold-400">
                        {item.document_name}
                      </span>
                      <span className="font-mono text-[11px] text-charcoal-500">
                        {item.date}
                      </span>
                    </div>
                    <div className="flex gap-2 items-center text-[11px]">
                      <span className="px-2 py-0.5 rounded bg-gold-100 text-gold-900 font-semibold">
                        Version {item.version || "1.0"}
                      </span>
                      <span className="text-charcoal-400">Status: {item.status}</span>
                    </div>
                    <p className="text-xs text-charcoal-600 dark:text-paper-300 pt-1">
                      {item.summary}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
