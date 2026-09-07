import React from "react";

const LANGUAGES = [
  "Auto-Detect",
  "English", "Hindi", "Tamil", "Telugu", "Kannada", "Malayalam",
  "Bengali", "Marathi", "Gujarati", "Punjabi", "Odia", "Urdu",
];

export default function LanguageSelector({ value, onChange }) {
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
        aria-label="Language selector"
        title={isOverride ? `Manual override active: answering in ${value}` : "Auto-detecting language per message"}
      >
        {LANGUAGES.map((lang) => (
          <option key={lang} value={lang}>
            {lang === "Auto-Detect" ? "🌐 Auto-Detect" : lang}
          </option>
        ))}
      </select>
      {isOverride && (
        <button
          onClick={() => onChange("Auto-Detect")}
          className="text-[10px] text-maroon-600 hover:text-maroon-800 underline title='Reset to Auto-Detect'"
          title="Reset to Auto-Detect"
        >
          Reset
        </button>
      )}
    </div>
  );
}

