const API_BASE = "http://localhost:8000";

function getToken() {
  return localStorage.getItem("doj_rag_token");
}

async function handle(res) {
  if (res.status === 401) {
    // Session expired/invalid - clear it and force a re-login.
    localStorage.removeItem("doj_rag_token");
    localStorage.removeItem("doj_rag_user");
    window.location.href = "/login";
    throw new Error("Session expired. Please log in again.");
  }
  if (!res.ok) {
    let detail = "Request failed";
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function authHeaders(extra = {}) {
  const token = getToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
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
  return handle(res);
}

// --- Chat / conversations ---------------------------------------------------

export async function sendChatMessage({ message, conversationId, language }) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      message,
      conversation_id: conversationId || null,
      language,
    }),
  });
  return handle(res);
}

export async function listConversations() {
  const res = await fetch(`${API_BASE}/api/conversations`, { headers: authHeaders() });
  return handle(res);
}

export async function getConversation(conversationId) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, { headers: authHeaders() });
  return handle(res);
}

export async function deleteConversation(conversationId) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handle(res);
}

export async function clearConversationMessages(conversationId) {
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handle(res);
}

export async function truncateConversation(conversationId, keepCount) {
  const res = await fetch(
    `${API_BASE}/api/conversations/${conversationId}/truncate?keep_count=${keepCount}`,
    { method: "PUT", headers: authHeaders() }
  );
  return handle(res);
}

export async function transcribeAudio(blob) {
  const form = new FormData();
  form.append("audio", blob, "recording.webm");
  const res = await fetch(`${API_BASE}/api/transcribe`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  return handle(res);
}

export async function sendFeedback({ conversationId, messageIndex, rating }) {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ conversation_id: conversationId, message_index: messageIndex, rating }),
  });
  return handle(res);
}
