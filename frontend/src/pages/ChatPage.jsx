import React, { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Sidebar from "../components/Sidebar.jsx";
import ChatWindow from "../components/ChatWindow.jsx";
import InputBar from "../components/InputBar.jsx";
import LanguageSelector from "../components/LanguageSelector.jsx";
import { useTextToSpeech, useVoiceRecorder } from "../hooks/useSpeech.js";
import {
  sendChatMessage,
  listConversations,
  getConversation,
  deleteConversation,
  clearConversationMessages,
  truncateConversation,
  transcribeAudio,
} from "../services/api.js";

// Note: no client-side user ID needed anymore - api.js attaches the
// logged-in user's JWT to every request, and the backend derives whose
// conversations these are from that token (see app/routes/deps.py).

export default function ChatPage() {
  const navigate = useNavigate();
  const { conversationId } = useParams(); // undefined on "/" - a fresh conversation

  const [conversations, setConversations] = useState([]);
  const [messages, setMessages] = useState([]);
  const [language, setLanguage] = useState("English");
  const [isSending, setIsSending] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [errorBanner, setErrorBanner] = useState(null);
  const [editingIndex, setEditingIndex] = useState(null);
  const [editingText, setEditingText] = useState(null);

  const { speak, stop, speakingId } = useTextToSpeech();
  const { isRecording, start: startRecording, stop: stopRecording } = useVoiceRecorder();

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

    (async () => {
      try {
        const detail = await getConversation(conversationId);
        if (!cancelled) setMessages(detail.messages);
      } catch (e) {
        if (!cancelled) setErrorBanner("Could not load that conversation.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const handleDeleteConversation = async (id) => {
    try {
      await deleteConversation(id);
      if (conversationId === id) navigate("/");
      refreshConversations();
    } catch (e) {
      setErrorBanner("Could not delete that conversation.");
    }
  };

  const handleSend = async (text) => {
    setErrorBanner(null);

    // If this send follows an "edit" click, truncate everything after the
    // edited message first so we replace the conversation's continuation
    // instead of branching a duplicate.
    if (editingIndex !== null && conversationId) {
      try {
        await truncateConversation(conversationId, editingIndex);
        setMessages((prev) => prev.slice(0, editingIndex));
      } catch (e) {
        setErrorBanner("Could not update the conversation before resending.");
        return;
      }
    }
    setEditingIndex(null);
    setEditingText(null);

    setMessages((prev) => [...prev, { sender: "user", message: text, language, sources: [] }]);
    setIsSending(true);

    try {
      const res = await sendChatMessage({ message: text, conversationId, language });
      setMessages((prev) => [
        ...prev,
        { sender: "bot", message: res.message, language: res.language, sources: res.sources || [] },
      ]);
      if (autoSpeak && voiceEnabled) speak(res.message, res.language, "auto");
      refreshConversations();

      // First message of a brand new conversation -> now move to its real URL.
      if (!conversationId) navigate(`/c/${res.conversation_id}`, { replace: true });
    } catch (e) {
      setErrorBanner(e.message || "Something went wrong. Please try again.");
      setMessages((prev) => [
        ...prev,
        { sender: "bot", message: "Sorry, I ran into an error processing that. Please try again.", language, sources: [] },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const handleEditMessage = (index, currentText) => {
    setEditingIndex(index);
    setEditingText(currentText);
  };

  const handleCancelEdit = () => {
    setEditingIndex(null);
    setEditingText(null);
  };

  const handleRecordStop = async () => {
    const blob = await stopRecording();
    if (!blob) return null;
    try {
      const res = await transcribeAudio(blob);
      return res.text;
    } catch (e) {
      setErrorBanner(e.message || "Could not transcribe audio.");
      return null;
    }
  };

  const handleSpeak = (msg, idx) => speak(msg.message, msg.language || language, idx);

  const activeTitle = conversationId
    ? conversations.find((c) => c.conversation_id === conversationId)?.title || "Conversation"
    : "New conversation";

  return (
    <div className="h-screen w-screen flex bg-paper-200 overflow-hidden">
      <Sidebar
        conversations={conversations}
        onDelete={handleDeleteConversation}
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
              Voice
            </label>
            <label className="flex items-center gap-1.5 text-xs text-charcoal-500 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoSpeak}
                onChange={(e) => setAutoSpeak(e.target.checked)}
                className="accent-maroon-500"
                disabled={!voiceEnabled}
              />
              Auto-speak
            </label>
            <LanguageSelector value={language} onChange={setLanguage} />
            {conversationId && (
              <button
                onClick={async () => {
                  await clearConversationMessages(conversationId);
                  setMessages([]);
                }}
                className="text-xs text-charcoal-400 hover:text-red-600 transition-colors"
              >
                Clear
              </button>
            )}
          </div>
        </header>

        {errorBanner && (
          <div className="bg-red-50 text-red-700 text-xs px-6 py-2 border-b border-red-100">
            {errorBanner}
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
        />

        <div className="max-w-3xl w-full mx-auto">
          <InputBar
            onSend={handleSend}
            onRecordStart={startRecording}
            onRecordStop={handleRecordStop}
            isRecording={isRecording}
            isSending={isSending}
            editingText={editingText}
            onCancelEdit={handleCancelEdit}
          />
        </div>
      </main>
    </div>
  );
}
