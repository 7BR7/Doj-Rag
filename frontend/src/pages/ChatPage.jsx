import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Sidebar from "../components/Sidebar.jsx";
import ChatWindow from "../components/ChatWindow.jsx";
import InputBar from "../components/InputBar.jsx";
import LanguageSelector from "../components/LanguageSelector.jsx";
import { useI18n } from "../i18n.jsx";
import { useTextToSpeech, useVoiceRecorder } from "../hooks/useSpeech.js";
import {
  streamChatMessage,
  listConversations,
  getConversation,
  deleteConversation,
  clearConversationMessages,
  createConversation,
  truncateConversation,
  transcribeAudio,
  exportConversation,
} from "../services/api.js";

// Note: no client-side user ID needed anymore - api.js attaches the
// logged-in user's JWT to every request, and the backend derives whose
// conversations these are from that token (see app/routes/deps.py).

export default function ChatPage() {
  const navigate = useNavigate();
  const { conversationId } = useParams(); // undefined on "/" - a fresh conversation

  const [conversations, setConversations] = useState([]);
  const [messages, setMessages] = useState([]);
  const { language, setLanguage, t } = useI18n();
  const [isSending, setIsSending] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [errorBanner, setErrorBanner] = useState(null);
  const [editingIndex, setEditingIndex] = useState(null);
  const [editingText, setEditingText] = useState(null);

  const { speak, stop, speakingId, unavailableNotice } = useTextToSpeech();
  const { isRecording, start: startRecording, stop: stopRecording } = useVoiceRecorder();

  // Tracks the in-flight /api/chat request so it can be cancelled - either
  // by an explicit "Stop" click, or automatically when the user chooses to
  // edit a message while a response is still being generated. The backend
  // may still finish generating and save that response in the background
  // (there's no cheap way to interrupt a local LLM mid-generation without a
  // streaming API), but the UI stops waiting on it immediately either way.
  const abortControllerRef = useRef(null);
  const sendInFlightRef = useRef(false);
  const skipConversationLoadRef = useRef(null);

  const cancelInFlightRequest = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsSending(false);
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const list = await listConversations();
      setConversations(list);
    } catch (e) {
      // Backend/Mongo may not be up yet - fail quietly in the sidebar.
    }
  }, []);

  useEffect(() => {
    refreshConversations();
  }, [refreshConversations]);

  // Load messages whenever the route's conversationId changes (including
  // navigating to "/" for a brand new conversation, which just clears state).
  useEffect(() => {
    let cancelled = false;
    setEditingIndex(null);
    setEditingText(null);
    setErrorBanner(null);

    if (!conversationId) {
      setMessages([]);
      return;
    }

    if (skipConversationLoadRef.current === conversationId) {
      skipConversationLoadRef.current = null;
      setMessages([]);
      return;
    }

    (async () => {
      try {
        const detail = await getConversation(conversationId);
        if (!cancelled) setMessages(detail.messages);
      } catch (e) {
        if (!cancelled) setErrorBanner(t("errorLoad"));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [conversationId, t]);

  const handleDeleteConversation = async (id) => {
    try {
      await deleteConversation(id);
      if (conversationId === id) navigate("/");
      refreshConversations();
    } catch (e) {
      setErrorBanner(t("errorDelete"));
    }
  };

  const handleNewConversation = async () => {
    cancelInFlightRequest();
    setErrorBanner(null);
    setEditingIndex(null);
    setEditingText(null);
    try {
      const created = await createConversation();
      skipConversationLoadRef.current = created.conversation_id;
      setMessages([]);
      navigate(`/c/${created.conversation_id}`);
      refreshConversations();
    } catch (e) {
      setErrorBanner(t("genericError"));
    }
  };

  const handleSend = async (text) => {
    if (sendInFlightRef.current) return;
    sendInFlightRef.current = true;
    setErrorBanner(null);

    // If this send follows an "edit" click, truncate everything after the
    // edited message first so we replace the conversation's continuation
    // instead of branching a duplicate.
    let effectiveConversationId = conversationId;
    if (editingIndex !== null && conversationId) {
      try {
        await truncateConversation(conversationId, editingIndex);
        setMessages((prev) => prev.slice(0, editingIndex));
      } catch (e) {
        setErrorBanner(t("errorUpdate"));
        sendInFlightRef.current = false;
        return;
      }
    }
    setEditingIndex(null);
    setEditingText(null);

    // Push the user's message, then a placeholder bot message that fills in
    // live as the stream arrives.
    const isManualOverride = language !== "Auto-Detect";
    const userLanguageLabel = isManualOverride ? language : "auto";
    const startTime = Date.now();

    setMessages((prev) => [
      ...prev,
      { sender: "user", message: text, language: userLanguageLabel, sources: [] },
      { sender: "bot", message: "", language: isManualOverride ? language : "", sources: [], streaming: true },
    ]);
    setIsSending(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const latestTextRef = { current: "" };

    const updateLastBotMessage = (updater) => {
      setMessages((prev) => {
        const next = [...prev];
        const lastIdx = next.length - 1;
        next[lastIdx] = { ...next[lastIdx], ...updater(next[lastIdx]) };
        return next;
      });
    };

    try {
      await streamChatMessage({
        message: text,
        conversationId: effectiveConversationId,
        language,
        overrideLanguage: isManualOverride,
        signal: controller.signal,
        onChunk: (delta) => {
          latestTextRef.current += delta;
          updateLastBotMessage((m) => ({ message: m.message + delta, translating: false }));
        },
        onPhase: (phase) => {
          if (phase === "translating") updateLastBotMessage(() => ({ translating: true }));
        },
        onReplace: (fullText) => {
          latestTextRef.current = fullText;
          updateLastBotMessage(() => ({ message: fullText, translating: false }));
        },
        onDone: (event) => {
          const latencyMs = Date.now() - startTime;
          updateLastBotMessage(() => ({
            sources: event.sources || [],
            language: event.language,
            intent: event.intent || null,
            relatedProvisions: event.related_provisions || [],
            latencyMs,
            streaming: false,
            translating: false,
          }));
          if (autoSpeak && voiceEnabled) speak(latestTextRef.current, event.language, "auto");
          refreshConversations();
          if (!effectiveConversationId) navigate(`/c/${event.conversation_id}`, { replace: true });
        },
        onError: (msg) => {
          setErrorBanner(msg || t("genericError"));
          updateLastBotMessage((m) => ({
            message: m.message || t("genericError"),
            streaming: false,
            translating: false,
          }));
        },
      });
    } catch (e) {
      if (e.name === "AbortError") {
        // User-initiated cancellation (Stop button, or editing mid-response) -
        // not a real error. Drop the empty/partial placeholder bot message
        // rather than leaving a half-written answer sitting in the thread.
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.sender === "bot" && last.streaming) return prev.slice(0, -1);
          return prev;
        });
      } else {
        setErrorBanner(e.message || t("genericError"));
      }
    } finally {
      abortControllerRef.current = null;
      sendInFlightRef.current = false;
      setIsSending(false);
    }
  };

  const handleEditMessage = (index, currentText) => {
    // If a response is still being generated, cancel it first so the user
    // isn't stuck waiting - editing should be immediate, not blocked behind
    // whatever's currently in flight.
    if (isSending) cancelInFlightRequest();
    setEditingIndex(index);
    setEditingText(currentText);
  };

  const handleCancelEdit = () => {
    setEditingIndex(null);
    setEditingText(null);
  };

  const handleRecordStop = async () => {
    const recorded = await stopRecording();
    if (!recorded) return null;
    // If browser Web Speech API provided instant transcription, return it directly with 0 latency
    if (recorded.transcriptText && recorded.transcriptText.trim()) {
      return recorded.transcriptText.trim();
    }
    // Fallback: send recorded audio to optimized Faster-Whisper backend
    try {
      const res = await transcribeAudio(recorded, language);
      return res.text;
    } catch (e) {
      setErrorBanner(t("errorTranscribe"));
      return null;
    }
  };

  const handleSpeak = (msg, idx) => {
    const voiceLang = (msg.language && msg.language !== "Auto-Detect" && msg.language !== "auto")
      ? msg.language
      : (language !== "Auto-Detect" ? language : undefined);
    speak(msg.message, voiceLang, idx);
  };

  const handleExport = async (format = "txt") => {
    if (!conversationId) {
      setErrorBanner(t("errorEmptyExport"));
      return;
    }
    try {
      await exportConversation(conversationId, format);
    } catch (err) {
      setErrorBanner(t("errorExport"));
    }
  };

  const activeTitle = conversationId
    ? conversations.find((c) => c.conversation_id === conversationId)?.title || t("conversation")
    : t("newConversation");

  return (
    <div className="h-screen w-screen flex bg-paper-200 overflow-hidden">
      <Sidebar
        conversations={conversations}
        onDelete={handleDeleteConversation}
        onNewConversation={handleNewConversation}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
      />

      <main className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between px-6 py-3.5 border-b border-charcoal-100 bg-paper-100">
          <div className="flex items-center gap-2.5">
            <div className="w-2 h-8 bg-maroon-500 rounded-sm" />
            <h1 className="font-serif text-lg text-charcoal-800">{activeTitle}</h1>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-charcoal-500 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={voiceEnabled}
                onChange={(e) => {
                  setVoiceEnabled(e.target.checked);
                  if (!e.target.checked) stop();
                }}
                className="accent-maroon-500"
              />
              {t("voice")}
            </label>
            <label className="flex items-center gap-1.5 text-xs text-charcoal-500 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoSpeak}
                onChange={(e) => setAutoSpeak(e.target.checked)}
                className="accent-maroon-500"
                disabled={!voiceEnabled}
              />
              {t("autoSpeak")}
            </label>
            <LanguageSelector value={language} onChange={setLanguage} />
            {conversationId && (
              <>
                <button
                  onClick={() => handleExport("txt")}
                  className="text-xs text-charcoal-600 hover:text-maroon-600 font-medium transition-colors border border-charcoal-200 px-2 py-1 rounded bg-white"
                  title={t("downloadConversation")}
                >
                  {t("export")}
                </button>
                <button
                  onClick={async () => {
                    await clearConversationMessages(conversationId);
                    setMessages([]);
                  }}
                  className="text-xs text-charcoal-400 hover:text-red-600 transition-colors"
                >
                  {t("clear")}
                </button>
              </>
            )}
          </div>
        </header>

        {errorBanner && (
          <div className="bg-red-50 text-red-700 text-xs px-6 py-2 border-b border-red-100">
            {errorBanner}
          </div>
        )}

        {unavailableNotice && (
          <div className="bg-amber-50 text-amber-700 text-xs px-6 py-2 border-b border-amber-100">
            {unavailableNotice}
          </div>
        )}

        <ChatWindow
          messages={messages}
          isLoading={isSending}
          onSpeak={handleSpeak}
          onStopSpeak={stop}
          speakingId={speakingId}
          voiceEnabled={voiceEnabled}
          onEdit={handleEditMessage}
          onSelectPrompt={handleSend}
          onExport={() => handleExport("txt")}
        />

        <div className="max-w-3xl w-full mx-auto">
          <InputBar
            onSend={handleSend}
            onRecordStart={() => startRecording(language !== "Auto-Detect" ? language : "English")}
            onRecordStop={handleRecordStop}
            isRecording={isRecording}
            isSending={isSending}
            editingText={editingText}
            onCancelEdit={handleCancelEdit}
            onStop={cancelInFlightRequest}
          />
        </div>
      </main>
    </div>
  );
}
