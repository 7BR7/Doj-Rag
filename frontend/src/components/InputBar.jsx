import React, { useState, useEffect, useRef } from "react";
import { useI18n } from "../i18n.jsx";

export default function InputBar({ onSend, onRecordStart, onRecordStop, isRecording, isSending, editingText, onCancelEdit, onStop }) {
  const { t } = useI18n();
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
          <span>{t("editingPrevious")}</span>
          <button
            onClick={() => {
              onCancelEdit();
              setText("");
            }}
            className="text-charcoal-400 hover:text-charcoal-700"
          >
            {t("cancel")}
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
          aria-label={isRecording ? t("stopRecording") : t("startRecording")}
          title={isRecording ? t("stopRecording") : t("askByVoice")}
        >
          🎤
        </button>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder={t("inputPlaceholder")}
          className="flex-1 resize-none bg-transparent outline-none text-sm py-1.5 max-h-32 placeholder:text-charcoal-300"
        />

        <button
          onClick={isSending ? onStop : handleSend}
          disabled={!isSending && !text.trim()}
          className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-colors disabled:opacity-30 ${
            isSending ? "bg-red-600 hover:bg-red-500 text-white" : "bg-maroon-600 hover:bg-maroon-500 text-paper-100"
          }`}
          aria-label={isSending ? t("stopGenerating") : t("send")}
          title={isSending ? t("stopGenerating") : t("send")}
        >
          {isSending ? "■" : "➤"}
        </button>
      </div>
      {isSending && (
        <p className="text-[11px] text-charcoal-400 mt-1.5 px-2">
          {t("generating")}
        </p>
      )}
      {isRecording && (
        <p className="text-[11px] text-red-600 mt-1.5 px-2">
          {t("recording")}
        </p>
      )}
    </div>
  );
}
