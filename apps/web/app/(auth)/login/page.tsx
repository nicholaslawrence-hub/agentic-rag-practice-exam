"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [magicSent, setMagicSent] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleGoogle() {
    await signIn("google", { callbackUrl: "/chat" });
  }

  async function handleMagicLink(e: React.FormEvent) {
    e.preventDefault();
    if (!email.endsWith("@berkeley.edu")) {
      alert("Please use your @berkeley.edu email address.");
      return;
    }
    setLoading(true);
    await signIn("resend", { email, redirect: false, callbackUrl: "/chat" });
    setLoading(false);
    setMagicSent(true);
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#003262] to-[#004a8f] flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-8">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[#003262]">MCB Tutor</h1>
          <p className="text-slate-500 text-sm mt-1">Sign in with your Berkeley account</p>
        </div>

        {magicSent ? (
          <div className="text-center py-6">
            <div className="text-4xl mb-4">📬</div>
            <h2 className="font-semibold text-lg mb-2">Check your email</h2>
            <p className="text-slate-500 text-sm">
              We sent a sign-in link to <strong>{email}</strong>. It expires in 10 minutes.
            </p>
          </div>
        ) : (
          <>
            {/* Google SSO */}
            <button
              onClick={handleGoogle}
              className="w-full flex items-center justify-center gap-3 border border-slate-200 rounded-xl py-3 font-medium hover:bg-slate-50 transition-colors mb-6"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              Continue with Google (@berkeley.edu)
            </button>

            <div className="relative mb-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200" />
              </div>
              <div className="relative flex justify-center text-xs text-slate-400">
                <span className="bg-white px-2">or</span>
              </div>
            </div>

            {/* Magic link */}
            <form onSubmit={handleMagicLink} className="space-y-3">
              <input
                type="email"
                placeholder="your@berkeley.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#003262]"
              />
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-[#003262] text-white rounded-xl py-3 font-medium text-sm hover:bg-[#004a8f] transition-colors disabled:opacity-50"
              >
                {loading ? "Sending…" : "Send sign-in link"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
