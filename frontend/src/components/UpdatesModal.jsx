import React, { useState, useEffect } from "react";
import { fetchUpdates, fetchMonitoringStatus, triggerMonitoringCheck } from "../services/api.js";
import { PanelError } from "./PanelStatus.jsx";

export default function UpdatesModal({ isOpen, onClose }) {
  const [updates, setUpdates] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [evts, mon] = await Promise.all([fetchUpdates(), fetchMonitoringStatus()]);
      setUpdates(evts || []);
      setSources(mon.sources || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleManualCheck = async () => {
    setChecking(true);
    try {
      await triggerMonitoringCheck();
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setChecking(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-charcoal-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-paper-100 dark:bg-charcoal-800 rounded-lg shadow-2xl border border-gold-500/30 w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-paper-300 dark:border-charcoal-700 bg-maroon-900 text-paper-100">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <h2 className="font-serif text-lg tracking-wide">Live Judiciary Monitoring & Source Updates</h2>
          </div>
          <button onClick={onClose} className="text-paper-100/70 hover:text-paper-100 text-lg">
            ✕
          </button>
        </div>

        {/* Source Status Strip */}
        <div className="p-4 border-b border-paper-300 dark:border-charcoal-700 bg-paper-200/50 dark:bg-charcoal-900/40 flex items-center justify-between">
          <div className="flex items-center gap-4 text-xs">
            <span className="font-semibold text-charcoal-700 dark:text-paper-200">Registered Official Sources:</span>
            <span className="px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 font-mono">
              {sources.length} Active Feeds
            </span>
          </div>
          <button
            onClick={handleManualCheck}
            disabled={checking}
            className="px-3.5 py-1.5 text-xs font-semibold rounded bg-maroon-800 hover:bg-maroon-700 text-gold-200 transition-colors flex items-center gap-1.5"
          >
            <span>🔄</span>
            {checking ? "Checking Sources..." : "Check Sources Now"}
          </button>
        </div>

        {/* Events Feed */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading && (
            <div className="py-16 text-center text-charcoal-400 text-xs">Loading monitoring events...</div>
          )}

          {!loading && error && <PanelError message={error} onRetry={loadData} />}

          {!loading && !error && updates.length === 0 && (
            <div className="py-16 text-center text-charcoal-500 text-xs">
              No recent update events recorded. Click "Check Sources Now" to poll registered judiciary feeds.
            </div>
          )}

          {!loading && !error && updates.map((evt) => (
            <div
              key={evt.event_id || evt._id}
              className="p-3.5 rounded border border-paper-300 dark:border-charcoal-700 bg-white dark:bg-charcoal-900/60 text-xs space-y-1"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-maroon-800 dark:text-gold-400 uppercase tracking-wider text-[10px]">
                  {evt.event_type}
                </span>
                <span className="text-[10px] text-charcoal-400">
                  {evt.timestamp ? new Date(evt.timestamp).toLocaleString() : "Just now"}
                </span>
              </div>
              <p className="font-medium text-charcoal-800 dark:text-paper-100">
                {evt.document_name}
              </p>
              {evt.details && (
                <p className="text-charcoal-600 dark:text-paper-300 text-[11px] leading-relaxed">
                  {evt.details}
                </p>
              )}
              <div className="pt-1 flex items-center gap-2 text-[10px] text-emerald-600 dark:text-emerald-400">
                <span>● Status: {evt.status || "Indexed successfully"}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
