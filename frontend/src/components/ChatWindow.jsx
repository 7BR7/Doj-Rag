import React, { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble.jsx";

export default function ChatWindow({
  messages,
  isLoading,
  onSpeak,
  onStopSpeak,
  speakingId,
  voiceEnabled,
  onEdit,
  onSelectPrompt,
}) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const PROMPT_SUGGESTIONS = [
    {
      title: "Article 19: Freedom of Speech",
      query: "What is Article 19 of the Constitution of India?",
      icon: "📜",
      desc: "6 fundamental freedoms & constitutional reasonable restrictions",
    },
    {
      title: "Article 14: Right to Equality",
      query: "Explain Article 14 equality before the law",
      icon: "⚖️",
      desc: "Equal protection of laws & prohibition of discrimination",
    },
    {
      title: "Article 21: Life & Liberty",
      query: "What is Article 21 and the right to privacy?",
      icon: "🛡️",
      desc: "Protection of life and personal liberty, due process",
    },
    {
      title: "Article 32: Constitutional Remedies",
      query: "What is Article 32 and writs of habeas corpus and mandamus?",
      icon: "🏛️",
      desc: "Heart and soul of the Constitution · Supreme Court writs",
    },
    {
      title: "Article 19 in Tamil (சரத்து 19)",
      query: "சரத்து 19 பற்றி தமிழில் கூறுங்கள்",
      icon: "🇮🇳",
      desc: "பேச்சு சுதந்திரம் மற்றும் 6 அடிப்படை உரிமைகள்",
    },
    {
      title: "Article 19 in Telugu (19వ అధికరణం)",
      query: "19వ అధికరణం గురించి వివరించండి",
      icon: "🇮🇳",
      desc: "భారత రాజ్యాంగంలోని వాక్ స్వాతంత్ర్యం మరియు 6 ప్రాథమిక హక్కులు",
    },
  ];

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-4 md:px-8 py-8 overflow-y-auto">
        <div className="max-w-2xl w-full flex flex-col items-center">
          {/* Scales of Justice SVG Emblem */}
          <div className="relative mb-5 flex items-center justify-center">
            <div className="w-20 h-20 rounded-full bg-paper-100 border-2 border-maroon-600/30 flex items-center justify-center shadow-lg shadow-maroon-900/5">
              <svg
                viewBox="0 0 24 24"
                className="w-10 h-10 text-maroon-700"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                {/* Central Pillar */}
                <line x1="12" y1="3" x2="12" y2="21" />
                <path d="M7 21h10" />
                {/* Balance Beam */}
                <line x1="4" y1="7" x2="20" y2="7" />
                {/* Left Pan */}
                <path d="M4 7l-2 7h6l-2-7" />
                {/* Right Pan */}
                <path d="M20 7l-2 7h6l-2-7" />
                {/* Fulcrum Finial */}
                <circle cx="12" cy="3.5" r="1" fill="currentColor" />
              </svg>
            </div>
            <span className="absolute -bottom-1 text-[10px] font-serif font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-maroon-600 text-white shadow-sm">
              DOJ-RAG
            </span>
          </div>

          <h2 className="font-serif text-2xl md:text-3xl font-semibold text-charcoal-800 mb-2">
            AI Judiciary Legal Assistant
          </h2>
          <p className="text-charcoal-500 text-sm max-w-lg mb-8 leading-relaxed">
            Instant, authoritative answers grounded in the Constitution of India,
            Bharatiya Nyaya Sanhita, Central Acts, and Supreme Court jurisprudence.
          </p>

          {/* Quick Prompt Cards */}
          <div className="w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-left">
            {PROMPT_SUGGESTIONS.map((item, idx) => (
              <button
                key={idx}
                onClick={() => onSelectPrompt && onSelectPrompt(item.query)}
                className="p-3.5 rounded-lg border border-charcoal-200/80 bg-white/90 hover:bg-paper-50 hover:border-maroon-400/80 transition-all duration-150 group shadow-sm hover:shadow text-left flex flex-col justify-between"
              >
                <div className="flex items-start gap-2.5 mb-1.5">
                  <span className="text-base shrink-0 select-none">{item.icon}</span>
                  <span className="text-xs font-semibold text-charcoal-800 group-hover:text-maroon-700 transition-colors">
                    {item.title}
                  </span>
                </div>
                <p className="text-[11px] text-charcoal-400 group-hover:text-charcoal-600 line-clamp-2 pl-6">
                  {item.desc}
                </p>
              </button>
            ))}
          </div>

          <div className="mt-8 flex items-center gap-2 text-xs text-charcoal-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
            <span>Multi-script legal NLP active (English, Tamil, Telugu, Hindi & 8 more)</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 md:px-10 py-6 space-y-4">
      <div className="max-w-3xl mx-auto space-y-4">
        {messages.map((msg, i) => (
          <MessageBubble
            key={i}
            index={i}
            msg={msg}
            onSpeak={(m) => onSpeak(m, i)}
            onStopSpeak={onStopSpeak}
            isSpeaking={speakingId === i}
            voiceEnabled={voiceEnabled}
            onEdit={onEdit}
          />
        ))}
        {/* No separate "typing" indicator needed - the streaming bot message
            bubble itself shows a blinking cursor (see MessageBubble) the
            moment it's added, even before the first token arrives. */}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
