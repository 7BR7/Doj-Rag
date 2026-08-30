import React, { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble.jsx";

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-white border border-charcoal-100 border-l-4 border-l-maroon-500 rounded-sm px-4 py-3 shadow-card flex gap-1">
        <span className="typing-dot w-1.5 h-1.5 rounded-full bg-charcoal-300" />
        <span className="typing-dot w-1.5 h-1.5 rounded-full bg-charcoal-300" />
        <span className="typing-dot w-1.5 h-1.5 rounded-full bg-charcoal-300" />
      </div>
    </div>
  );
}

export default function ChatWindow({ messages, isLoading, onSpeak, onStopSpeak, speakingId, voiceEnabled, onEdit }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
        <div className="w-16 h-16 seal-ring text-maroon-500 flex items-center justify-center mb-4 relative">
          <span className="font-serif text-2xl">§</span>
        </div>
        <h2 className="font-serif text-2xl text-charcoal-800 mb-2">Ask a legal question</h2>
        <p className="text-charcoal-400 text-sm max-w-sm">
          Try "What is Article 21?" or "What are fundamental rights?" — answers
          are drawn from the Constitution, Acts, Rules, and judgments you've
          processed.
        </p>
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
        {isLoading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
