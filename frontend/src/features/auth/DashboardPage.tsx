"use client";

import { useAccessToken } from "./useAccessToken";
import "./auth.css";

// Placeholder: the backend redirects here after login. Real dashboard is a separate feature.
export default function DashboardPage() {
  const session = useAccessToken();
  if (session === "loading") return <main className="auth-page" />;
  return (
    <main className="auth-page">
      <h1 className="auth-title">Dashboard</h1>
    </main>
  );
}
