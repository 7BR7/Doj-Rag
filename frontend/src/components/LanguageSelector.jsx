import React from "react";

const LANGUAGES = [
  "English", "Hindi", "Tamil", "Telugu", "Kannada", "Malayalam",
  "Bengali", "Marathi", "Gujarati", "Punjabi", "Odia", "Urdu",
];

export default function LanguageSelector({ value, onChange }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="text-xs bg-white border border-charcoal-200 rounded px-2 py-1.5 text-charcoal-700 focus:outline-none focus:ring-1 focus:ring-maroon-500 cursor-pointer"
      aria-label="Preferred language"
    >
      {LANGUAGES.map((lang) => (
        <option key={lang} value={lang}>
          {lang}
        </option>
      ))}
    </select>
  );
}
