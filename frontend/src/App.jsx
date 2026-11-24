import { useEffect, useRef, useState } from "react";

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

const newSessionId = () =>
  "s-" + (crypto.randomUUID ? crypto.randomUUID().slice(0, 8) : Math.random().toString(36).slice(2, 10));

function errorText(status, data) {
  if (status === 503) return "All AI providers are unavailable right now. Please try again in a moment.";
  if (status === 422) return "That message was not accepted. Messages must be 1 to 4000 characters.";
  if (data && typeof data.detail === "string") return data.detail;
  return "Something went wrong. Please try again.";
}

export default function App() {
  const [sessionId] = useState(newSessionId); // new session on every page load
  const [items, setItems] = useState([]);
  const [input, setInput] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items, busy]);

  async function send() {
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    setItems((p) => [...p, { kind: "user", text: message }]);
    setBusy(true);
    try {
      const body = { session_id: sessionId, message };
      if (systemPrompt.trim()) body.system_prompt = systemPrompt.trim();
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      let data = null;
      try { data = await res.json(); } catch { /* non-JSON body */ }
      if (!res.ok) {
        setItems((p) => [...p, { kind: "error", text: errorText(res.status, data) }]);
      } else {
        setItems((p) => [...p, { kind: "assistant", text: data.reply, meta: data.metadata }]);
      }
    } catch {
      setItems((p) => [...p, { kind: "error", text: "Could not reach the server. Check your connection and try again." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>LLM Chatbot</h1>
        <span className="sid">session {sessionId}</span>
      </header>

      <details className="sys">
        <summary>System prompt</summary>
        <textarea
          data-testid="system-prompt-input"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          placeholder="Optional. Applies to this session, e.g. 'Answer like a pirate.'"
          rows={2}
        />
      </details>

      <main>
        {items.length === 0 && <p className="empty">Send a message to start the conversation.</p>}
        {items.map((it, i) => {
          if (it.kind === "user") return <div key={i} className="bubble user">{it.text}</div>;
          if (it.kind === "error") return <div key={i} className="bubble error" role="alert" data-testid="error-message">{it.text}</div>;
          const m = it.meta;
          return (
            <div key={i} className="bubble assistant" data-testid="assistant-message">
              <div className="text">{it.text}</div>
              <dl className="meta">
                <div><dt>Source</dt><dd data-testid="meta-source" className={m.resolution_source === "LLM_CACHE" ? "cache" : "live"}>{m.resolution_source}</dd></div>
                <div><dt>Model</dt><dd data-testid="meta-model">{m.model}</dd></div>
                <div><dt>Latency</dt><dd data-testid="meta-latency">{m.latency_ms} ms</dd></div>
                <div><dt>Input tokens</dt><dd data-testid="meta-input-tokens">{m.input_tokens}</dd></div>
                <div><dt>Output tokens</dt><dd data-testid="meta-output-tokens">{m.output_tokens}</dd></div>
              </dl>
            </div>
          );
        })}
        {busy && <div className="bubble assistant pending">Thinking…</div>}
        <div ref={endRef} />
      </main>

      <footer>
        <textarea
          data-testid="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          placeholder="Type a message"
          rows={1}
          maxLength={4000}
        />
        <button data-testid="send-button" onClick={send} disabled={busy}>Send</button>
      </footer>
    </div>
  );
}
