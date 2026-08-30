import React from "react";

function sourceLabel(s) {
  const bits = [];
  if (s.article) bits.push(`Article ${s.article}`);
  if (s.section) bits.push(`Section ${s.section}`);
  if (s.rule) bits.push(`Rule ${s.rule}`);
  return bits.length ? bits.join(", ") : "Reference";
}

export default function SourcePanel({ sources }) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-3 border-t border-charcoal-100 pt-3 space-y-2">
      {sources.map((s, i) => (
        <div
          key={i}
          className="flex items-start gap-3 text-xs bg-paper-200 border border-charcoal-100 rounded px-3 py-2"
        >
          <span className="font-mono text-maroon-600 shrink-0">{String(i + 1).padStart(2, "0")}</span>
          <div>
            <p className="font-medium text-charcoal-800">{sourceLabel(s)}</p>
            <p className="text-charcoal-500 mt-0.5">
              {s.document}
              {s.part ? ` · ${s.part}` : ""}
              {s.chapter ? ` · ${s.chapter}` : ""}
              {s.page_start ? ` · p.${s.page_start}${s.page_end && s.page_end !== s.page_start ? `–${s.page_end}` : ""}` : ""}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
