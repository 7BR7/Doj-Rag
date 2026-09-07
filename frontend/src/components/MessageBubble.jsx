import React, { useState } from "react";
import SourcePanel from "./SourcePanel.jsx";

function CopyButton({ text, className }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (_) {
      // Clipboard API can be blocked (e.g. no HTTPS/localhost permission) -
      // fail silently rather than showing an error for a non-critical action.
    }
  };

  if (!text) return null;

  return (
    <button onClick={handleCopy} className={className} title="Copy">
      {copied ? "✓ Copied" : "⧉ Copy"}
    </button>
  );
}

export default function MessageBubble({ msg, index, onSpeak, onStopSpeak, isSpeaking, voiceEnabled, onEdit }) {
  const [showSources, setShowSources] = useState(false);
  const isUser = msg.sender === "user";

  if (isUser) {
    return (
      <div className="flex justify-end group">
        <div className="max-w-[75%] flex items-start gap-2">
          <div className="opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center gap-1 mt-2 shrink-0">
            <button
              onClick={() => onEdit(index, msg.message)}
              className="text-charcoal-400 hover:text-maroon-600 text-xs"
              title="Edit and resend"
              aria-label="Edit message"
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
          <p className="text-[11px] text-maroon-500 mt-2 italic">Translating into {msg.language}…</p>
        )}

        <div className="flex items-center gap-3 mt-3 text-[11px] text-charcoal-400">
          {msg.language && msg.language !== "Auto-Detect" && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-paper-200 text-charcoal-600 border border-charcoal-200 font-sans" title={`Language: ${msg.language}`}>
              🌐 {msg.language}
            </span>
          )}
          {msg.sources && msg.sources.length > 0 && (
            <button
              onClick={() => setShowSources((s) => !s)}
              className="uppercase tracking-wide text-maroon-600 hover:text-maroon-500 font-medium"
            >
              {showSources ? "Hide source" : "View source"}
            </button>
          )}
          {!msg.streaming && <CopyButton text={msg.message} className="hover:text-charcoal-700" />}
          {voiceEnabled && !msg.streaming && (
            <>
              {!isSpeaking ? (
                <button
                  onClick={() => onSpeak(msg)}
                  className="hover:text-charcoal-700 flex items-center gap-1 transition-colors"
                  title="Listen to audio speech"
                >
                  ▶ Play
                </button>
              ) : (
                <button
                  onClick={onStopSpeak}
                  className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-maroon-100 text-maroon-800 text-[11px] font-medium border border-maroon-300 hover:bg-maroon-200 transition-colors shadow-sm"
                  title="Stop audio playback"
                >
                  <span className="flex items-end gap-0.5 h-3 pb-0.5">
                    <span className="w-0.5 h-2.5 bg-maroon-600 animate-pulse" />
                    <span className="w-0.5 h-1.5 bg-maroon-600 animate-pulse" style={{ animationDelay: "150ms" }} />
                    <span className="w-0.5 h-3 bg-maroon-600 animate-pulse" style={{ animationDelay: "300ms" }} />
                    <span className="w-0.5 h-2 bg-maroon-600 animate-pulse" style={{ animationDelay: "450ms" }} />
                  </span>
                  <span>■ Stop</span>
                </button>
              )}
              <button
                onClick={() => onSpeak(msg)}
                className="hover:text-charcoal-700 transition-colors"
                title="Replay audio from beginning"
              >
                ↻ Replay
              </button>
            </>
          )}
        </div>

        {showSources && <SourcePanel sources={msg.sources} />}
      </div>
    </div>
  );
}
