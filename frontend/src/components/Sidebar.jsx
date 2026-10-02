import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { useI18n } from "../i18n.jsx";

const DATE_LOCALES = {
  English: "en-IN", Hindi: "hi-IN", Tamil: "ta-IN", Urdu: "ur-IN", Punjabi: "pa-IN",
  Odia: "or-IN", Telugu: "te-IN", Kannada: "kn-IN", Malayalam: "ml-IN", Bengali: "bn-IN",
  Marathi: "mr-IN", Gujarati: "gu-IN",
};

function formatDate(iso, language) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(DATE_LOCALES[language] || "en-IN", { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export default function Sidebar({ conversations, onDelete, onNewConversation, collapsed, onToggleCollapse }) {
  const navigate = useNavigate();
  const { conversationId: activeId } = useParams();
  const { user, logout } = useAuth();
  const { t, uiLanguage } = useI18n();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <aside
      className={`h-full flex flex-col bg-maroon-900 text-paper-100 transition-all duration-200 ${
        collapsed ? "w-14" : "w-72"
      }`}
    >
      <div className="flex items-center justify-between px-4 py-5 border-b border-maroon-700">
        {!collapsed && (
          <div className="flex items-center gap-2.5">
            <div className="relative w-8 h-8 shrink-0 text-gold-400 seal-ring flex items-center justify-center">
              <span className="font-serif text-sm">न्या</span>
            </div>
            <div>
              <p className="font-serif text-base leading-tight text-paper-100">DOJ-RAG</p>
              <p className="text-[10px] uppercase tracking-[0.18em] text-gold-400">
                {t("legalAssistant")}
              </p>
            </div>
          </div>
        )}
        <button
          onClick={onToggleCollapse}
          className="text-maroon-100/70 hover:text-paper-100 transition-colors p-1"
          aria-label={t("toggleSidebar")}
        >
          {collapsed ? "»" : "«"}
        </button>
      </div>

      <div className="px-3 pt-4">
        <button
          onClick={onNewConversation}
          className="w-full flex items-center gap-2 justify-center rounded border border-gold-500/50 bg-gold-500/10 hover:bg-gold-500/20 text-gold-100 text-sm py-2 transition-colors"
        >
          <span className="text-gold-400">+</span>
          {!collapsed && <span>{t("newConversation")}</span>}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4 space-y-1">
        {conversations.length === 0 && !collapsed && (
          <p className="text-maroon-200/70 text-xs px-2 py-4">
            {t("emptyConversations")}
          </p>
        )}
        {conversations.map((c) => (
          <div
            key={c.conversation_id}
            className={`group flex items-center rounded px-2 py-2 cursor-pointer text-sm transition-colors ${
              activeId === c.conversation_id
                ? "bg-maroon-700 text-paper-100"
                : "text-maroon-100/80 hover:bg-maroon-800"
            }`}
            onClick={() => navigate(`/c/${c.conversation_id}`)}
          >
            <div className="flex-1 min-w-0">
              {!collapsed && (
                <>
                  <p className="truncate">{c.title}</p>
                  <p className="text-[10px] text-maroon-300 mt-0.5">{formatDate(c.updated_at, uiLanguage)}</p>
                </>
              )}
            </div>
            {!collapsed && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(c.conversation_id);
                }}
                className="opacity-0 group-hover:opacity-100 text-maroon-300 hover:text-red-300 text-xs px-1 transition-opacity"
                aria-label={t("deleteConversation")}
                title={t("deleteConversation")}
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </nav>

      {!collapsed && (
        <div className="px-4 py-3 border-t border-maroon-700 space-y-2">
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <p className="text-xs text-paper-100 truncate">{user?.username}</p>
              <p className="text-[10px] text-maroon-300">{t("signedIn")}</p>
            </div>
            <button
              onClick={handleLogout}
              className="text-[11px] text-maroon-200 hover:text-paper-100 shrink-0 ml-2"
            >
              {t("logout")}
            </button>
          </div>
          <p className="text-[10px] text-maroon-300 leading-relaxed">
            {t("disclaimer")}
          </p>
        </div>
      )}
    </aside>
  );
}
