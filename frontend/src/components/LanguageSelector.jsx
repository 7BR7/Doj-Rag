import React from "react";
import { getNativeLanguageName, UI_LANGUAGES, useI18n } from "../i18n.jsx";

export default function LanguageSelector({ value, onChange }) {
  const { t } = useI18n();
  const isOverride = value && value !== "Auto-Detect";

  return (
    <div className="flex items-center gap-1.5">
      <select
        value={value || "Auto-Detect"}
        onChange={(e) => onChange(e.target.value)}
        className={`text-xs border rounded px-2 py-1.5 focus:outline-none focus:ring-1 cursor-pointer transition-colors ${
          isOverride
            ? "bg-maroon-50 border-maroon-400 text-maroon-800 font-medium focus:ring-maroon-500"
            : "bg-white border-charcoal-200 text-charcoal-700 focus:ring-maroon-500"
        }`}
        aria-label={t("languageSelector")}
        title={isOverride ? t("manualOverride", { language: getNativeLanguageName(value) }) : t("autoDetectTitle")}
      >
        {UI_LANGUAGES.map((lang) => (
          <option key={lang} value={lang}>
            {lang === "Auto-Detect" ? `🌐 ${t("autoDetect")}` : getNativeLanguageName(lang)}
          </option>
        ))}
      </select>
      {isOverride && (
        <button
          onClick={() => onChange("Auto-Detect")}
          className="text-[10px] text-maroon-600 hover:text-maroon-800 underline"
          title={t("reset")}
        >
          {t("reset")}
        </button>
      )}
    </div>
  );
}

