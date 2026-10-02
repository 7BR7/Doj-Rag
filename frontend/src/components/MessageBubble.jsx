import React, { useState } from "react";
import SourcePanel from "./SourcePanel.jsx";
import { getNativeLanguageName, useI18n } from "../i18n.jsx";

function CopyButton({ text, className }) {
  const [copied, setCopied] = useState(false);
  const { t } = useI18n();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (_) {
      // Clipboard API can be blocked — fail silently.
    }
  };

  if (!text) return null;

  return (
    <button onClick={handleCopy} className={className} title={t("copy")}>
      {copied ? t("copied") : t("copy")}
    </button>
  );
}

/** Inline performance badge — shows LLM response latency */
function LatencyBadge({ ms, label }) {
  if (!ms) return null;
  const color = ms < 2000 ? "text-green-600" : ms < 8000 ? "text-amber-600" : "text-red-600";
  return (
    <span className={`text-[10px] font-mono ${color}`} title={label}>
      ⚡ {ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`}
    </span>
  );
}

/** Intent badge — shows detected query intent */
function IntentBadge({ intent, t }) {
  if (!intent || intent === "GENERAL") return null;
  const colors = {
    DEFINITION: "bg-blue-100 text-blue-700",
    RIGHTS: "bg-purple-100 text-purple-700",
    PROCEDURE: "bg-teal-100 text-teal-700",
    COMPARISON: "bg-orange-100 text-orange-700",
    TIMELINE: "bg-indigo-100 text-indigo-700",
    PENALTY: "bg-red-100 text-red-700",
  };
  const cls = colors[intent] || "bg-gray-100 text-gray-600";
  const labels = {
    DEFINITION: "intentDefinition", RIGHTS: "intentRights", PROCEDURE: "intentProcedure",
    COMPARISON: "intentComparison", TIMELINE: "intentTimeline", PENALTY: "intentPenalty",
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${cls}`} title={t("detectedIntent")}>
      {t(labels[intent] || intent)}
    </span>
  );
}

export default function MessageBubble({
  msg, index, onSpeak, onStopSpeak, isSpeaking, voiceEnabled, onEdit, onExport
}) {
  const [showSources, setShowSources] = useState(false);
  const { t } = useI18n();
  const isUser = msg.sender === "user";

  if (isUser) {
    return (
      <div className="flex justify-end group">
        <div className="max-w-[75%] flex items-start gap-2">
          <div className="opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center gap-1 mt-2 shrink-0">
            <button
              onClick={() => onEdit(index, msg.message)}
              className="text-charcoal-400 hover:text-maroon-600 text-xs"
              title={t("editResend")}
              aria-label={t("editMessage")}
            >
              ✎
            </button>
            <CopyButton text={msg.message} className="text-charcoal-400 hover:text-maroon-600 text-[10px]" />
          </div>
          <div className="bg-charcoal-700 text-paper-100 rounded-md rounded-tr-sm px-4 py-3 text-sm leading-relaxed shadow-card">
            {msg.message}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] bg-white border border-charcoal-100 border-l-4 border-l-maroon-500 rounded-sm px-4 py-3 shadow-card">
        <p className="text-sm leading-relaxed text-charcoal-800 whitespace-pre-wrap font-serif">
          {msg.message}
          {msg.streaming && (
            <span className="inline-block w-1.5 h-3.5 bg-maroon-400 ml-0.5 align-middle animate-pulse" />
          )}
        </p>

        {msg.translating && (
          <p className="text-[11px] text-maroon-500 mt-2 italic">{t("translatingInto", { language: msg.language })}</p>
        )}

        {/* Action bar */}
        <div className="flex items-center gap-3 mt-3 text-[11px] text-charcoal-400 flex-wrap">
          {/* Language badge */}
          {msg.language && msg.language !== "Auto-Detect" && msg.language !== "auto" && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded bg-paper-200 text-charcoal-600 border border-charcoal-200 font-sans"
              title={`${t("language")}: ${getNativeLanguageName(msg.language)}`}
            >
              🌐 {getNativeLanguageName(msg.language)}
            </span>
          )}

          {/* Intent badge */}
          {msg.intent && <IntentBadge intent={msg.intent} t={t} />}

          {/* Latency badge */}
          <LatencyBadge ms={msg.latencyMs} label={t("responseTime")} />

          {/* View sources */}
          {msg.sources && msg.sources.length > 0 && (
            <button
              onClick={() => setShowSources((s) => !s)}
              className="uppercase tracking-wide text-maroon-600 hover:text-maroon-500 font-medium"
            >
              {showSources ? t("hideSource") : t("viewSource")}
            </button>
          )}

          {/* Copy */}
          {!msg.streaming && <CopyButton text={msg.message} className="hover:text-charcoal-700" />}

          {/* Export */}
          {!msg.streaming && onExport && (
            <button
              onClick={onExport}
              className="hover:text-charcoal-700 transition-colors"
              title={t("exportConversation")}
            >
              ↓ Export
            </button>
          )}

          {/* Voice playback */}
          {voiceEnabled && !msg.streaming && (
            <>
              {!isSpeaking ? (
                <button
                  onClick={() => onSpeak(msg)}
                  className="hover:text-charcoal-700 flex items-center gap-1 transition-colors"
                  title={t("listen")}
                >
                  ▶ Play
                </button>
              ) : (
                <button
                  onClick={onStopSpeak}
                  className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-maroon-100 text-maroon-800 text-[11px] font-medium border border-maroon-300 hover:bg-maroon-200 transition-colors shadow-sm"
                  title={t("stopPlayback")}
                >
                  <span className="flex items-end gap-0.5 h-3 pb-0.5">
                    <span className="w-0.5 h-2.5 bg-maroon-600 animate-pulse" />
                    <span className="w-0.5 h-1.5 bg-maroon-600 animate-pulse" style={{ animationDelay: "150ms" }} />
                    <span className="w-0.5 h-3 bg-maroon-600 animate-pulse" style={{ animationDelay: "300ms" }} />
                    <span className="w-0.5 h-2 bg-maroon-600 animate-pulse" style={{ animationDelay: "450ms" }} />
                  </span>
                  <span>■ {t("stopPlayback")}</span>
                </button>
              )}
              <button
                onClick={() => onSpeak(msg)}
                className="hover:text-charcoal-700 transition-colors"
                title={t("replay")}
              >
                ↻ {t("replay")}
              </button>
            </>
          )}
        </div>

        {/* Related provisions from knowledge graph */}
        {msg.relatedProvisions && msg.relatedProvisions.length > 0 && !msg.streaming && (
          <div className="mt-3 pt-2 border-t border-charcoal-100">
            <p className="text-[10px] uppercase tracking-wide text-charcoal-400 mb-1.5">{t("relatedProvisions")}</p>
            <div className="flex flex-wrap gap-1.5">
              {msg.relatedProvisions.map((p, i) => (
                <span
                  key={i}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200"
                  title={`${p.relation} (${p.node_type})`}
                >
                  {p.label}
                </span>
              ))}
            </div>
          </div>
        )}

        {showSources && <SourcePanel sources={msg.sources} />}
      </div>
    </div>
  );
}
