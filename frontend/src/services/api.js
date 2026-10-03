export const API_BASE = "http://localhost:8000";

function getToken() {
  return localStorage.getItem("doj_rag_token");
}

async function handle(res, { authRequired = false } = {}) {
  if (!res.ok) {
    let detail = "Request failed";
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch (_) {}

    if (res.status === 401 && authRequired) {
      // Session expired/invalid - clear it and force a re-login.
      localStorage.removeItem("doj_rag_token");
      localStorage.removeItem("doj_rag_user");
      window.location.href = "/login";
      throw new Error("Session expired. Please log in again.");
    }

    throw new Error(detail);
  }
  return res.json();
}

function authHeaders(extra = {}) {
  const token = getToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 12000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error("The server did not respond in time. Check that the backend is running, then retry.");
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

// --- Auth ------------------------------------------------------------------

export async function registerUser({ username, email, password }) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, email: email || null, password }),
  });
  return handle(res);
}

export async function loginUser({ username, password }) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return handle(res);
}

export async function fetchCurrentUser() {
  const res = await fetch(`${API_BASE}/api/auth/me`, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

// --- Chat / conversations ---------------------------------------------------

/**
 * Streams a chat response as newline-delimited JSON events (see backend
 * app/services/chat_service.stream_chat_message for event shapes) and
 * invokes the given callbacks as they arrive. Pass `signal` from an
 * AbortController to make this cancellable - aborting closes the
 * connection, which stops generation on the backend too instead of just
 * ignoring the result client-side.
 */
export async function streamChatMessage({ message, conversationId, documentId = null, language, overrideLanguage = false, signal, onChunk, onPhase, onReplace, onDone, onError }) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      message,
      conversation_id: conversationId || null,
      document_id: documentId,
      language: language || "Auto-Detect",
      override_language: overrideLanguage,
    }),
    signal,
  });

  if (res.status === 401) {
    localStorage.removeItem("doj_rag_token");
    localStorage.removeItem("doj_rag_user");
    window.location.href = "/login";
    return;
  }
  if (!res.ok || !res.body) {
    let detail = "Request failed";
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch (_) {}
    onError?.(detail);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIndex;
    while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (!line) continue;

      let event;
      try {
        event = JSON.parse(line);
      } catch (_) {
        continue;
      }

      if (event.type === "chunk") onChunk?.(event.text);
      else if (event.type === "phase") onPhase?.(event.phase);
      else if (event.type === "replace") onReplace?.(event.text);
      else if (event.type === "error") onError?.(event.message);
      else if (event.type === "done") onDone?.(event);
    }
  }
}

export async function listConversations() {
  const res = await fetch(`${API_BASE}/api/conversations`, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

export async function createConversation() {
  const res = await fetch(`${API_BASE}/api/conversations`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handle(res, { authRequired: true });
}

export async function getConversation(conversationId) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

export async function deleteConversation(conversationId) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handle(res, { authRequired: true });
}

export async function clearConversationMessages(conversationId) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handle(res, { authRequired: true });
}

export async function truncateConversation(conversationId, keepCount) {
  const res = await fetch(
    `${API_BASE}/api/conversations/${conversationId}/truncate?keep_count=${keepCount}`,
    { method: "PUT", headers: authHeaders() }
  );
  return handle(res, { authRequired: true });
}

export async function transcribeAudio(blob, language = null) {
  const form = new FormData();
  form.append("audio", blob, "recording.webm");
  const url = language && language !== "Auto-Detect"
    ? `${API_BASE}/api/transcribe?language=${encodeURIComponent(language)}`
    : `${API_BASE}/api/transcribe`;
  const res = await fetch(url, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handle(res, { authRequired: true });
}

export async function sendFeedback({ conversationId, messageIndex, rating }) {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ conversation_id: conversationId, message_index: messageIndex, rating }),
  });
  return handle(res, { authRequired: true });
}

// --- Export -----------------------------------------------------------------

export async function exportConversation(conversationId, format = "txt") {
  const res = await fetch(`${API_BASE}/api/export`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ conversation_id: conversationId, format }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Export failed");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const ext = format === "md" ? "md" : "txt";
  const a = document.createElement("a");
  a.href = url;
  a.download = `judiciary_ai_${conversationId.slice(0, 8)}.${ext}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// --- NLP Analysis -----------------------------------------------------------

export async function analyzeNlp(text) {
  const res = await fetch(`${API_BASE}/api/nlp/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return handle(res);
}

export async function getRelatedProvisions(nodeType, identifier) {
  const res = await fetch(
    `${API_BASE}/api/nlp/graph/related?node_type=${encodeURIComponent(nodeType)}&identifier=${encodeURIComponent(identifier)}`
  );
  return handle(res);
}

export async function getHealthStatus() {
  const res = await fetchWithTimeout(`${API_BASE}/api/health`);
  return handle(res);
}

// --- Intelligence & Judiciary Endpoints -------------------------------------

export async function fetchDocuments() {
  const res = await fetchWithTimeout(`${API_BASE}/api/documents`, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

export async function fetchDocumentDetail(docId) {
  const res = await fetchWithTimeout(`${API_BASE}/api/documents/${encodeURIComponent(docId)}`, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

export async function searchLegalDocuments(query, docId = null) {
  let url = `${API_BASE}/api/search?q=${encodeURIComponent(query)}`;
  if (docId) url += `&document_id=${encodeURIComponent(docId)}`;
  const res = await fetchWithTimeout(url, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

export async function compareVersions(documentId, versionA, versionB, section = null) {
  const res = await fetchWithTimeout(`${API_BASE}/api/compare`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      document_id: documentId,
      version_a: versionA,
      version_b: versionB,
      section: section || null,
    }),
  });
  return handle(res, { authRequired: true });
}

export async function fetchTimeline(docId = null) {
  let url = `${API_BASE}/api/timeline`;
  if (docId) url += `?document_id=${encodeURIComponent(docId)}`;
  const res = await fetchWithTimeout(url, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

export async function fetchUpdates() {
  const res = await fetchWithTimeout(`${API_BASE}/api/updates`, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

export async function fetchMonitoringStatus() {
  const res = await fetchWithTimeout(`${API_BASE}/api/monitoring/status`, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

export async function triggerMonitoringCheck() {
  const res = await fetchWithTimeout(`${API_BASE}/api/monitoring/check`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
  });
  return handle(res, { authRequired: true });
}

export async function fetchFullGraph(limit = 100) {
  const res = await fetchWithTimeout(`${API_BASE}/api/graph/full?limit=${limit}`, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}

export async function fetchSystemStats() {
  const res = await fetchWithTimeout(`${API_BASE}/api/stats`, { headers: authHeaders() });
  return handle(res, { authRequired: true });
}
