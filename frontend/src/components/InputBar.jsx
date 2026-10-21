import React, { useState, useEffect, useRef } from "react";
import { useI18n } from "../i18n.jsx";

export default function InputBar({
  onSend,
  onRecordStart,
  onRecordStop,
  isRecording,
  isSending,
  editingText,
  onCancelEdit,
  onStop,
  micError,         // string | null — microphone permission / capture errors
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [isTranscribing, setIsTranscribing] = useState(false);
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
    if (isTranscribing) return; // debounce: ignore clicks during Whisper processing
    if (isRecording) {
      setIsTranscribing(true);
      try {
        const transcribed = await onRecordStop();
        if (transcribed) setText((prev) => (prev ? `${prev} ${transcribed}` : transcribed));
      } finally {
        setIsTranscribing(false);
      }
    } else {
      onRecordStart();
    }
  };

  const isEditing = editingText !== null && editingText !== undefined;
  // Mic button is busy while recording or while Whisper is processing
  const micBusy = isRecording || isTranscribing;

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
          disabled={isTranscribing}
          className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-colors ${
            isRecording
              ? "bg-red-600 text-white animate-pulse"
              : isTranscribing
              ? "bg-amber-500 text-white animate-spin"
              : "bg-charcoal-100 text-charcoal-600 hover:bg-charcoal-200"
          }`}
          aria-label={isRecording ? t("stopRecording") : isTranscribing ? t("transcribing") : t("startRecording")}
          title={isRecording ? t("stopRecording") : isTranscribing ? t("transcribing") : t("askByVoice")}
        >
          {isTranscribing ? "⏳" : "🎤"}
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

      {/* Status messages — only one shown at a time, in priority order */}
      {isSending && (
        <p className="text-[11px] text-charcoal-400 mt-1.5 px-2">
          {t("generating")}
        </p>
      )}
      {!isSending && isTranscribing && (
        <p className="text-[11px] text-amber-600 mt-1.5 px-2">
          ⏳ {t("transcribing") || "Transcribing…"}
        </p>
      )}
      {!isSending && !isTranscribing && isRecording && (
        <p className="text-[11px] text-red-600 mt-1.5 px-2 flex items-center gap-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          {t("recording")}
        </p>
      )}
      {!isSending && !isTranscribing && !isRecording && micError && (
        <p className="text-[11px] text-red-600 mt-1.5 px-2">
          ⚠ {micError}
        </p>
      )}
    </div>
  );
}
