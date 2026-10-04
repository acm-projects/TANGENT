"use client";

import "./auth.css";

export default function LoginPage() {
  // Full-page navigation (not axios): the backend 302s to Google. Signup and login are the same button.
  const onContinue = () => {
    window.location.assign(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/auth/login/google`);
  };

  return (
    <main className="auth-page">
      <section className="auth-card">
        <h1 className="auth-title">Welcome to TANGENT</h1>
        <p className="auth-muted">Sign in or create an account to continue.</p>
        <button type="button" className="auth-button" onClick={onContinue}>
          Continue with Google
        </button>
      </section>
    </main>
  );
}
