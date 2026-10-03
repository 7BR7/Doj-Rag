import React from "react";

export function PanelError({ message, onRetry }) {
  return (
    <div className="py-12 px-5 text-center text-sm text-red-700" role="alert">
      <p>{message || "Could not load this panel. Check the backend connection and try again."}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 px-3 py-1.5 rounded border border-red-300 text-red-700 hover:bg-red-50"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function PanelEmpty({ children }) {
  return (
    <div className="py-12 px-5 text-center text-sm text-charcoal-500" role="status">
      {children}
    </div>
  );
}
