import React, { useState, useEffect } from "react";
import { fetchFullGraph } from "../services/api.js";
import { PanelEmpty, PanelError } from "./PanelStatus.jsx";

export default function GraphModal({ isOpen, onClose }) {
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadGraph();
    }
  }, [isOpen]);

  const loadGraph = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFullGraph(80);
      setGraphData(data);
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
            <span className="text-gold-400 font-serif text-lg">🕸️</span>
            <h2 className="font-serif text-lg tracking-wide">Legal Knowledge Graph Explorer</h2>
          </div>
          <button onClick={onClose} className="text-paper-100/70 hover:text-paper-100 text-lg">
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 p-4 grid grid-cols-3 gap-4 overflow-hidden">
          <div className="col-span-2 overflow-y-auto p-4 rounded border border-paper-300 dark:border-charcoal-700 bg-white dark:bg-charcoal-900/60">
            {loading && <div className="py-20 text-center text-xs text-charcoal-400">Rendering knowledge graph...</div>}

            {!loading && error && <PanelError message={error} onRetry={loadGraph} />}

            {!loading && !error && graphData.nodes.length === 0 && (
              <PanelEmpty>The knowledge graph has no nodes yet. Check that its data file is available, then retry.</PanelEmpty>
            )}

            {!loading && !error && graphData.nodes.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {graphData.nodes.map((n) => (
                  <button
                    key={n.id}
                    onClick={() => setSelectedNode(n)}
                    className={`px-2.5 py-1.5 rounded-full text-xs font-medium border transition-all ${
                      selectedNode?.id === n.id
                        ? "bg-maroon-800 text-gold-300 border-gold-400 scale-105"
                        : "bg-paper-200 dark:bg-charcoal-800 text-charcoal-800 dark:text-paper-200 border-paper-300 dark:border-charcoal-700 hover:border-gold-500/50"
                    }`}
                  >
                    <span className="text-[10px] opacity-60 mr-1">[{n.node_type || "Provision"}]</span>
                    {n.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="col-span-1 p-4 rounded border border-paper-300 dark:border-charcoal-700 bg-paper-200/50 dark:bg-charcoal-900/40 overflow-y-auto">
            <h3 className="font-serif text-xs font-bold uppercase tracking-wider text-charcoal-700 dark:text-gold-400 mb-2">
              Node Relationships
            </h3>
            {selectedNode ? (
              <div className="space-y-3 text-xs">
                <div>
                  <p className="text-[10px] text-charcoal-500 uppercase">Selected</p>
                  <p className="font-bold text-maroon-900 dark:text-paper-100">{selectedNode.label}</p>
                  <p className="text-charcoal-400 text-[11px]">Type: {selectedNode.node_type}</p>
                </div>

                <div className="pt-2 border-t border-paper-300 dark:border-charcoal-700">
                  <p className="text-[10px] text-charcoal-500 uppercase mb-1">Direct Relationships</p>
                  <div className="space-y-1.5">
                    {graphData.edges
                      .filter((e) => e.source === selectedNode.id || e.target === selectedNode.id)
                      .slice(0, 10)
                      .map((e, idx) => (
                        <div key={idx} className="p-2 rounded bg-white dark:bg-charcoal-800 text-[11px] border border-paper-300 dark:border-charcoal-700">
                          <span className="text-maroon-700 dark:text-gold-400 font-mono text-[10px]">
                            {e.relation}
                          </span>
                          <p className="text-charcoal-600 dark:text-paper-200 truncate">
                            → {e.source === selectedNode.id ? e.target : e.source}
                          </p>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-xs text-charcoal-500">
                Click any provision or concept node to view its constitutional relationships, enabling articles, and amendment history.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
