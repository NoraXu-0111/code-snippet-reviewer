import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  request,
  useResource,
  type DiscussionDetail,
  type DiscussionTurn,
} from "./api";

type Submission = { message: string; clientRequestId: string };
const isActive = (turn: DiscussionTurn) =>
  turn.status === "queued" || turn.status === "running";

function readPending(key: string): Submission | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) ?? "null");
    return value &&
      typeof value.message === "string" &&
      typeof value.clientRequestId === "string"
      ? value
      : null;
  } catch {
    return null;
  }
}

export function Discussion({ findingId }: { findingId: string }) {
  const storageKey = `discussion-pending:${findingId}`;
  const [pending, setPending] = useState<Submission | null>(() =>
    readPending(storageKey),
  );
  const [message, setMessage] = useState(pending?.message ?? "");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const inFlight = useRef(false);
  const composer = useRef<HTMLTextAreaElement>(null);
  const historyList = useRef<HTMLOListElement>(null);
  const path = `/findings/${findingId}/discussion`;
  const {
    data,
    error,
    retry: refresh,
  } = useResource<DiscussionDetail>(path, (data) => data.turns.some(isActive));
  const active = data?.turns.some(isActive) ?? false;
  const latest = data?.turns.at(-1);

  useEffect(() => {
    if (historyList.current) {
      historyList.current.scrollTop = historyList.current.scrollHeight;
    }
  }, [latest?.id, latest?.status, latest?.attempt]);

  function remember(value: Submission | null) {
    setPending(value);
    // Session storage preserves a request key across reloads after a lost response.
    // If storage is unavailable, in-memory replay remains available.
    try {
      if (value) sessionStorage.setItem(storageKey, JSON.stringify(value));
      else sessionStorage.removeItem(storageKey);
    } catch {
      /* Private browsing/storage limits must not break submission. */
    }
  }

  useEffect(() => {
    if (
      pending &&
      data?.turns.some(
        (turn) => turn.clientRequestId === pending.clientRequestId,
      )
    ) {
      remember(null);
      setMessage("");
      setActionError("");
    }
  }, [data, pending]);

  async function send() {
    if (inFlight.current || (!pending && (active || !message.trim()))) return;
    inFlight.current = true;
    setBusy(true);
    setActionError("");
    const submission = pending ?? {
      message,
      clientRequestId: crypto.randomUUID(),
    };
    remember(submission);
    try {
      await request<DiscussionTurn>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(submission),
      });
      remember(null);
      setMessage("");
    } catch (error) {
      // A 4xx/503 response confirms rejection. Network/5xx errors may have
      // happened after persistence: keep the exact payload and replay its key.
      if (
        error instanceof ApiError &&
        (error.status < 500 || error.status === 503)
      )
        remember(null);
      setActionError(
        error instanceof Error
          ? error.message
          : "Could not send your question.",
      );
    } finally {
      refresh();
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function retryTurn(turn: DiscussionTurn) {
    if (inFlight.current || active || pending) return;
    inFlight.current = true;
    setBusy(true);
    setActionError("");
    try {
      await request<DiscussionTurn>(`/discussion-turns/${turn.id}/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ attempt: turn.attempt }),
      });
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Could not retry this reply.",
      );
    } finally {
      // Includes stale retry conflicts and lost responses; always fetch truth.
      refresh();
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="discussion" aria-label="Finding discussion">
      <p className="discussion-help">
        Ask about this finding. OpenAI receives the snippet, finding, and your
        most recent 10 completed exchanges. Replies do not change your code.
      </p>
      {!data && !error && (
        <p role="status" className="muted">
          Loading conversation…
        </p>
      )}
      {error && (
        <p className="review-error" role="alert">
          Unable to refresh conversation: {error}{" "}
          <button className="text-button" onClick={refresh}>
            Refresh conversation
          </button>
        </p>
      )}
      {data?.turns.length === 0 && (
        <p className="discussion-empty">
          Need an example, or think this is a false positive? Ask here.
        </p>
      )}
      <ol
        ref={historyList}
        className="discussion-history"
        aria-label="Conversation history"
        aria-live="polite"
        aria-relevant="additions text"
      >
        {data?.turns.map((turn, index) => (
          <li key={turn.id}>
            <div className="chat-message chat-user">
              <span className="chat-author">You</span>
              <p>{turn.userMessage}</p>
            </div>
            <div className="chat-message chat-assistant">
              <span className="chat-author">AI</span>
              {turn.status === "succeeded" && <p>{turn.assistantMessage}</p>}
              {isActive(turn) && (
                <p role="status">
                  <span className="spinner" aria-hidden="true" />
                  {turn.status === "queued"
                    ? "Waiting to reply…"
                    : "Thinking…"}{" "}
                  You can leave and come back.
                </p>
              )}
              {turn.status === "failed" && (
                <>
                  <p className="review-error">{turn.error}</p>
                  {index === data.turns.length - 1 ? (
                    <button
                      className="secondary"
                      disabled={busy || active || !!pending}
                      onClick={() => retryTurn(turn)}
                    >
                      Retry reply
                    </button>
                  ) : (
                    <button
                      className="text-button"
                      disabled={busy || active || !!pending}
                      onClick={() => {
                        setMessage(turn.userMessage);
                        composer.current?.focus();
                      }}
                    >
                      Use question again
                    </button>
                  )}
                </>
              )}
            </div>
          </li>
        ))}
      </ol>
      {actionError && (
        <p className="review-error" role="alert">
          {actionError}
        </p>
      )}
      {pending && !busy && (
        <div className="submission-recovery" role="status">
          <p>
            We haven’t confirmed whether your question was saved. Check again to
            recover it without sending a duplicate.
          </p>
          <button className="secondary" onClick={send}>
            Check submission
          </button>
        </div>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <label htmlFor={`question-${findingId}`}>Ask a follow-up</label>
        <textarea
          id={`question-${findingId}`}
          ref={composer}
          rows={3}
          value={message}
          disabled={busy || active || !!pending || !data}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Why is this a problem?"
          aria-describedby={`question-limit-${findingId}`}
        />
        <div className="discussion-compose-footer">
          <span
            id={`question-limit-${findingId}`}
            className={
              Array.from(message).length > 4000 ? "review-error" : "muted"
            }
          >
            {Array.from(message).length} / 4,000
          </span>
          <button
            className="primary"
            type="submit"
            disabled={
              busy ||
              active ||
              !!pending ||
              !data ||
              !message.trim() ||
              Array.from(message).length > 4000
            }
          >
            {busy ? "Sending…" : "Send question"}
          </button>
        </div>
      </form>
    </section>
  );
}
