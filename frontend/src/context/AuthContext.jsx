import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { loginUser, registerUser, fetchCurrentUser } from "../services/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem("doj_rag_user");
    return stored ? JSON.parse(stored) : null;
  });
  const [loading, setLoading] = useState(true);

  // On load, verify any stored token is still valid rather than trusting it blindly.
  useEffect(() => {
    const token = localStorage.getItem("doj_rag_token");
    if (!token) {
      setLoading(false);
      return;
    }
    fetchCurrentUser()
      .then((u) => {
        setUser(u);
        localStorage.setItem("doj_rag_user", JSON.stringify(u));
      })
      .catch(() => {
        localStorage.removeItem("doj_rag_token");
        localStorage.removeItem("doj_rag_user");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username, password) => {
    const res = await loginUser({ username, password });
    localStorage.setItem("doj_rag_token", res.access_token);
    localStorage.setItem("doj_rag_user", JSON.stringify(res.user));
    setUser(res.user);
    return res.user;
  }, []);

  const register = useCallback(async (username, email, password) => {
    const res = await registerUser({ username, email, password });
    localStorage.setItem("doj_rag_token", res.access_token);
    localStorage.setItem("doj_rag_user", JSON.stringify(res.user));
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("doj_rag_token");
    localStorage.removeItem("doj_rag_user");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
