import React, { useState } from "react";
import SourcePanel from "./SourcePanel.jsx";

export default function MessageBubble({ msg, index, onSpeak, onStopSpeak, isSpeaking, voiceEnabled, onEdit }) {
  const [showSources, setShowSources] = useState(false);
  const isUser = msg.sender === "user";

  if (isUser) {
    return (
      <div className="flex justify-end group">
        <div className="max-w-[75%] flex items-start gap-2">
          <button
            onClick={() => onEdit(index, msg.message)}
            className="opacity-0 group-hover:opacity-100 transition-opacity text-charcoal-400 hover:text-maroon-600 text-xs mt-3 shrink-0"
            title="Edit and resend"
            aria-label="Edit message"
          >
            ✎
          </button>
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
        </p>

        <div className="flex items-center gap-3 mt-3 text-[11px] text-charcoal-400">
          {msg.sources && msg.sources.length > 0 && (
            <button
              onClick={() => setShowSources((s) => !s)}
              className="uppercase tracking-wide text-maroon-600 hover:text-maroon-500 font-medium"
            >
              {showSources ? "Hide source" : "View source"}
            </button>
          )}
          {voiceEnabled && (
            <>
              {!isSpeaking ? (
                <button onClick={() => onSpeak(msg)} className="hover:text-charcoal-700">
                  ▶ Play
                </button>
              ) : (
                <button onClick={onStopSpeak} className="hover:text-charcoal-700">
                  ■ Stop
                </button>
              )}
              <button onClick={() => onSpeak(msg)} className="hover:text-charcoal-700">
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
