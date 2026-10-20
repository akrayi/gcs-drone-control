import React, { useEffect, useRef, useState } from "react";
import Login from "./components/Login";
import FlightMap from "./components/FlightMap";
import AdminPanel from "./components/AdminPanel";

export default function App() {
  const [token, setToken] = useState("");
  const [data, setData] = useState(null);
  const [connection, setConnection] = useState("offline");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [users, setUsers] = useState([]);
  const [target, setTarget] = useState({ x: 25, y: 25 });
  const [retry, setRetry] = useState(null);
  const socket = useRef(null);
  const state = data?.state;
  const role = data?.user.role;

  async function api(path, options = {}) {
    const res = await fetch("/api" + path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    const body = await res.json();
    if (res.status === 401 && token) logout();
    if (!res.ok)
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : body.reason || JSON.stringify(body.detail),
      );
    return body;
  }
  function logout() {
    setToken("");
    setData(null);
    setUsers([]);
    setRetry(null);
    setConnection("offline");
    socket.current?.close();
  }

  useEffect(() => {
    if (!token) return;
    let stopped = false,
      timer;
    let lastMessage = Date.now();
    const watchdog = setInterval(() => {
      if (Date.now() - lastMessage > 4000) {
        setConnection("offline");
        socket.current?.close();
      }
    }, 1000);
    function connect() {
      lastMessage = Date.now();
      setConnection("connecting");
      const ws = new WebSocket(
        `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/ws`,
      );
      socket.current = ws;
      ws.onopen = () => ws.send(JSON.stringify({ token }));
      ws.onmessage = (e) => {
        if (!stopped) {
          lastMessage = Date.now();
          setData(JSON.parse(e.data));
          setConnection("live");
        }
      };
      ws.onclose = (e) => {
        if (stopped) return;
        setConnection("offline");
        if (e.code === 1008) {
          setNotice("Session expired or access revoked. Please sign in again.");
          logout();
        } else timer = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      clearInterval(watchdog);
      socket.current?.close();
    };
  }, [token]);

  async function login(e) {
    e.preventDefault();
    setBusy(true);
    setNotice("");
    const form = new FormData(e.currentTarget);
    try {
      const result = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(form)),
      });
      setToken(result.access_token);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy(false);
    }
  }
  async function send(action, previous = null) {
    setBusy(true);
    setNotice("");
    const payload = previous || {
      request_id: crypto.randomUUID(),
      action,
      ...(action !== "RETURN_HOME" ? { expected_version: state.version } : {}),
      ...(action === "MOVE" ? target : {}),
    };
    try {
      const result = await api("/commands", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setNotice(
        `${action}: ${result.reason}. Shared state v${result.state.version}.`,
      );
      setRetry(null);
    } catch (error) {
      setNotice(
        error.message === "STALE_VERSION"
          ? "Another operator changed the drone. Review the live state, then send a new command."
          : error.message,
      );
      // Keep exact payload to resolve unknown outcomes safely after a network failure.
      setRetry(
        error instanceof TypeError ||
          error.message.includes("Database unavailable")
          ? payload
          : null,
      );
    } finally {
      setBusy(false);
    }
  }
  async function loadUsers() {
    try {
      setUsers(await api("/users"));
    } catch (e) {
      setNotice(e.message);
    }
  }
  useEffect(() => {
    if (role === "admin") loadUsers();
  }, [role, token]);
  async function createUser(e) {
    e.preventDefault();
    const form = e.currentTarget;
    setBusy(true);
    try {
      await api("/users", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      });
      form.reset();
      await loadUsers();
      setNotice("Account created. Share its password securely.");
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy(false);
    }
  }
  async function updateUser(username, changes) {
    setBusy(true);
    try {
      await api(`/users/${encodeURIComponent(username)}`, {
        method: "POST",
        body: JSON.stringify(changes),
      });
      await loadUsers();
      setNotice(`Updated ${username}; their previous sessions are revoked.`);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setBusy(false);
    }
  }

  const locked = busy || connection !== "live";
  return (
    <div className="shell">
      <header>
        <div className="brand">
          <svg className="logo" viewBox="0 0 40 40" aria-hidden="true">
            <path
              d="M6 6L34 34M6 34L34 6"
              stroke="currentColor"
              strokeWidth="2"
            />
            <circle cx="8" cy="8" r="6" />
            <circle cx="32" cy="8" r="6" />
            <circle cx="8" cy="32" r="6" />
            <circle cx="32" cy="32" r="6" />
            <rect x="15" y="12" width="10" height="16" rx="3" />
          </svg>
          <div>
            GCS<span className="brand-sub">ZERO-TRUST FLIGHT SYSTEM</span>
          </div>
        </div>
        <div className="header-right">
          <span className="sim">SIMULATION ONLY</span>
          {token && (
            <>
              <span>
                {data?.user.username} · {role}
              </span>
              <button className="quiet" onClick={logout}>
                Sign out
              </button>
            </>
          )}
        </div>
      </header>
      {!token ? (
        <Login busy={busy} onSubmit={login} />
      ) : (
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">GROUND CONTROL STATION / DRONE 01</div>
              <h1>Mission overview</h1>
            </div>
            <div className={`connection ${connection}`}>
              <span />{" "}
              {connection === "live"
                ? "Live · synchronized"
                : "Connection interrupted · controls paused"}
            </div>
          </div>
          <div className="stats">
            <Stat label="Flight status" value={state?.mode || "CONNECTING"} />
            <Stat label="Altitude" value={`${state?.altitude ?? "—"} m`} />
            <Stat
              label="Position"
              value={state ? `${state.x}, ${state.y}` : "—"}
            />
            <Stat label="State version" value={`v${state?.version ?? "—"}`} />
          </div>
          {state?.safety_latched && (
            <div className="safety">
              Safety lock active · RETURN_HOME has grounded the drone. An admin
              must clear the lock before a new takeoff.
            </div>
          )}
          <div className="mission-grid">
            <FlightMap state={state} target={target} setTarget={setTarget} />
            <section className="panel controls">
              <div className="eyebrow">COMMAND CENTER</div>
              <h2>Flight controls</h2>
              <p className="muted">
                {role === "viewer"
                  ? "Observer access. Live telemetry and command history are available."
                  : "Commands apply to the shared drone for every connected operator."}
              </p>
              <div className="coords">
                <label>
                  Target X
                  <input
                    type="number"
                    min="-100"
                    max="100"
                    value={target.x}
                    onChange={(e) =>
                      setTarget({ ...target, x: Number(e.target.value) })
                    }
                  />
                </label>
                <label>
                  Target Y
                  <input
                    type="number"
                    min="-100"
                    max="100"
                    value={target.y}
                    onChange={(e) =>
                      setTarget({ ...target, y: Number(e.target.value) })
                    }
                  />
                </label>
              </div>
              <button
                className="primary"
                disabled={
                  locked ||
                  role === "viewer" ||
                  state?.mode !== "GROUNDED" ||
                  state?.safety_latched
                }
                onClick={() => send("TAKEOFF")}
              >
                Take off
              </button>
              <button
                disabled={
                  locked || role === "viewer" || state?.mode !== "AIRBORNE"
                }
                onClick={() => send("MOVE")}
              >
                Move to target
              </button>
              <button
                disabled={
                  locked || role === "viewer" || state?.mode !== "AIRBORNE"
                }
                onClick={() => send("LAND")}
              >
                Land in place
              </button>
              <div className="divider" />
              <button
                className="danger"
                disabled={connection !== "live" || role === "viewer"}
                onClick={() => send("RETURN_HOME")}
              >
                Return home & lock
              </button>
              <p className="muted small">
                Safety override: ignores stale versions and blocks subsequent
                takeoffs.
              </p>
              {role === "admin" && (
                <button
                  disabled={locked || !state?.safety_latched}
                  onClick={() => send("CLEAR_SAFETY")}
                >
                  Clear safety lock
                </button>
              )}
            </section>
          </div>
          <section className="panel activity">
            <div className="panel-heading">
              <h2>Shared command history</h2>
              <span className="muted">Last 20 commands</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Operator</th>
                    <th>Command</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.events.map((event) => (
                    <tr key={event.request_id}>
                      <td>{new Date(event.created_at).toLocaleTimeString()}</td>
                      <td>{event.username}</td>
                      <td>{event.action}</td>
                      <td>
                        <span
                          className={
                            event.reason === "APPLIED" ? "success" : "warning"
                          }
                        >
                          {event.reason}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {!data?.events.length && (
                    <tr>
                      <td colSpan="4" className="muted">
                        No commands yet. Start a flight to see activity here.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
          {role === "admin" && (
            <AdminPanel
              users={users}
              busy={busy}
              currentUsername={data.user.username}
              loadUsers={loadUsers}
              createUser={createUser}
              updateUser={updateUser}
            />
          )}
        </main>
      )}
      {notice && (
        <div className="notice" role="status">
          {notice}
          {retry && (
            <button disabled={busy} onClick={() => send(retry.action, retry)}>
              Retry same request
            </button>
          )}
          <button
            className="quiet"
            aria-label="Dismiss message"
            onClick={() => setNotice("")}
          >
            ×
          </button>
        </div>
      )}
      <footer>
        <span>GCS / ZERO-TRUST LAB</span>
        <span>JWT identity · OPA policy · PostgreSQL arbitration</span>
      </footer>
    </div>
  );
}
function Stat({ label, value }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
