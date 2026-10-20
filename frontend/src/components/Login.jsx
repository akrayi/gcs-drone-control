import React from "react";
export default function Login({ busy, onSubmit }) {
  return (
    <main className="login-layout">
      <section>
        <div className="eyebrow">ONE DRONE. ONE SHARED TRUTH.</div>
        <h1>
          Mission control,
          <br />
          <em>with trust verified.</em>
        </h1>
        <p>
          Coordinate a shared drone in real time. Every command is
          authenticated, authorized, and safely arbitrated.
        </p>
        <div className="login-notes">
          <span>01 · Identity verified</span>
          <span>02 · Policy checked</span>
          <span>03 · State synchronized</span>
        </div>
      </section>
      <form className="panel login" onSubmit={onSubmit}>
        <div className="eyebrow">OPERATOR ACCESS</div>
        <h2>Sign in to your station</h2>
        <label>
          Username
          <input
            name="username"
            autoComplete="username"
            required
            maxLength="64"
            placeholder="admin"
          />
        </label>
        <label>
          Password
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength="128"
          />
        </label>
        <button className="primary" disabled={busy}>
          {" "}
          {busy ? "Verifying…" : "Enter mission control"}
        </button>
        <p className="muted">
          First sign-in: use the admin credentials generated during setup. Your
          admin can create pilot and viewer accounts.
        </p>
      </form>
    </main>
  );
}
