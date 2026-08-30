import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    setSubmitting(true);
    try {
      await register(username.trim(), email.trim(), password);
      navigate("/");
    } catch (err) {
      setError(err.message || "Could not create your account.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-paper-200 px-4">
      <div className="w-full max-w-sm bg-white border border-charcoal-100 rounded shadow-card p-8">
        <div className="flex flex-col items-center mb-6">
          <div className="w-12 h-12 seal-ring text-maroon-500 flex items-center justify-center mb-3 relative">
            <span className="font-serif text-lg">न्या</span>
          </div>
          <h1 className="font-serif text-xl text-charcoal-800">Create your account</h1>
          <p className="text-xs text-charcoal-400 mt-1">Your conversation history stays private to your account</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-charcoal-500 mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              minLength={3}
              autoFocus
              className="w-full border border-charcoal-200 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-maroon-500"
            />
          </div>
          <div>
            <label className="block text-xs text-charcoal-500 mb-1">Email (optional)</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-charcoal-200 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-maroon-500"
            />
          </div>
          <div>
            <label className="block text-xs text-charcoal-500 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              className="w-full border border-charcoal-200 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-maroon-500"
            />
          </div>
          <div>
            <label className="block text-xs text-charcoal-500 mb-1">Confirm password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full border border-charcoal-200 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-maroon-500"
            />
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-maroon-600 hover:bg-maroon-500 disabled:opacity-50 text-paper-100 text-sm py-2.5 rounded transition-colors"
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="text-xs text-charcoal-400 text-center mt-5">
          Already have an account?{" "}
          <Link to="/login" className="text-maroon-600 hover:text-maroon-500 font-medium">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
