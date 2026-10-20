import React, { useState } from "react";
export default function AdminPanel({
  users,
  busy,
  currentUsername,
  loadUsers,
  createUser,
  updateUser,
}) {
  return (
    <section className="panel admin">
      <div className="panel-heading">
        <div>
          <div className="eyebrow">ADMINISTRATION</div>
          <h2>Operators & access</h2>
        </div>
        <button className="quiet" onClick={loadUsers}>
          Refresh
        </button>
      </div>
      <form className="user-form" onSubmit={createUser}>
        <label>
          Username
          <input
            name="username"
            pattern="[a-zA-Z0-9_-]{3,64}"
            required
            placeholder="new-pilot"
          />
        </label>
        <label>
          Initial password
          <input
            name="password"
            type="password"
            minLength="12"
            maxLength="128"
            required
            autoComplete="new-password"
          />
        </label>
        <label>
          Role
          <select name="role">
            <option>pilot</option>
            <option>viewer</option>
            <option>admin</option>
          </select>
        </label>
        <button className="primary" disabled={busy}>
          Create account
        </button>
      </form>
      <div className="users">
        {users.map((u) => (
          <UserRow
            key={u.username}
            user={u}
            self={u.username === currentUsername}
            busy={busy}
            onUpdate={updateUser}
          />
        ))}
      </div>
    </section>
  );
}
function UserRow({ user, self, busy, onUpdate }) {
  const [password, setPassword] = useState("");
  return (
    <div className="user-row">
      <strong>
        {user.username} {self && "(you)"}
      </strong>
      <span className={user.active ? "success" : "warning"}>
        {user.active ? "Active" : "Disabled"}
      </span>
      <select
        aria-label={`Role for ${user.username}`}
        value={user.role}
        disabled={self || busy}
        onChange={(e) => onUpdate(user.username, { role: e.target.value })}
      >
        <option>admin</option>
        <option>pilot</option>
        <option>viewer</option>
      </select>
      <button
        disabled={self || busy}
        onClick={() => onUpdate(user.username, { active: !user.active })}
      >
        {user.active ? "Disable" : "Enable"}
      </button>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onUpdate(user.username, { password });
          setPassword("");
        }}
      >
        <input
          aria-label={`New password for ${user.username}`}
          type="password"
          autoComplete="new-password"
          placeholder="New password (12+ characters)"
          minLength="12"
          maxLength="128"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button disabled={busy}>Reset password</button>
      </form>
    </div>
  );
}
