import React, { useState, useEffect, useRef } from "react";

export default function InputBar({ onSend, onRecordStart, onRecordStop, isRecording, isSending, editingText, onCancelEdit }) {
  const [text, setText] = useState("");
  const textareaRef = useRef(null);

  useEffect(() => {
    if (editingText !== null && editingText !== undefined) {
      setText(editingText);
      textareaRef.current?.focus();
    }
  }, [editingText]);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;
    onSend(trimmed);
    setText("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    if (e.key === "Escape" && editingText !== null) {
      onCancelEdit();
      setText("");
    }
  };

  const handleMicClick = async () => {
    if (isRecording) {
      const transcribed = await onRecordStop();
      if (transcribed) setText((prev) => (prev ? `${prev} ${transcribed}` : transcribed));
    } else {
      onRecordStart();
    }
  };

  const isEditing = editingText !== null && editingText !== undefined;

  return (
    <div className="border-t border-charcoal-100 bg-paper-100 px-4 py-3">
      {isEditing && (
        <div className="flex items-center justify-between max-w-none text-[11px] text-maroon-600 mb-1.5 px-1">
          <span>Editing a previous message — sending will replace everything after it.</span>
          <button
            onClick={() => {
              onCancelEdit();
              setText("");
            }}
            className="text-charcoal-400 hover:text-charcoal-700"
          >
            Cancel
          </button>
        </div>
      )}
      <div className={`flex items-end gap-2 bg-white border rounded px-3 py-2 shadow-card ${isEditing ? "border-maroon-400" : "border-charcoal-200"}`}>
        <button
          onClick={handleMicClick}
          className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-colors ${
            isRecording
              ? "bg-red-600 text-white animate-pulse"
              : "bg-charcoal-100 text-charcoal-600 hover:bg-charcoal-200"
          }`}
          aria-label={isRecording ? "Stop recording" : "Start recording"}
          title={isRecording ? "Stop recording" : "Ask by voice"}
        >
          🎤
        </button>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Ask about an Article, Section, Rule, or any legal question…"
          className="flex-1 resize-none bg-transparent outline-none text-sm py-1.5 max-h-32 placeholder:text-charcoal-300"
        />

        <button
          onClick={handleSend}
          disabled={!text.trim() || isSending}
          className="shrink-0 w-9 h-9 rounded-full bg-maroon-600 text-paper-100 flex items-center justify-center disabled:opacity-30 hover:bg-maroon-500 transition-colors"
          aria-label="Send message"
        >
          ➤
        </button>
      </div>
      {isRecording && (
        <p className="text-[11px] text-red-600 mt-1.5 px-2">
          Recording… tap the microphone again to stop and transcribe.
        </p>
      )}
    </div>
  );
}
