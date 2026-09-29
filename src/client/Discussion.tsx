import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  formatDate,
  request,
  useResource,
  type DiscussionDetail,
  type DiscussionTurn,
} from "./api";

import type { components } from "../shared/api-types";
type ConversationRecord = components["schemas"]["DiscussionConversation"];

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

function readId(key: string): string | null {
  try {
    const value = sessionStorage.getItem(key);
    return value &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        value,
      )
      ? value
      : null;
  } catch {
    return null;
  }
}

export function Discussion({ findingId }: { findingId: string }) {
  const selectedKey = `discussion-selected:${findingId}`;
  const creationKey = `discussion-create:${findingId}`;
  const [selected, setSelected] = useState(
    () => readId(selectedKey) ?? findingId,
  );
  const [pendingCreate, setPendingCreate] = useState<string | null>(() =>
    readId(creationKey),
  );
  const [creating, setCreating] = useState(false);
  const [sending, setSending] = useState(false);
  const [creationError, setCreationError] = useState("");
  const creationInFlight = useRef(false);
  const path = `/findings/${findingId}/discussion${selected === findingId ? "" : `?conversationId=${encodeURIComponent(selected)}`}`;
  const {
    data,
    error,
    retry: refresh,
  } = useResource<DiscussionDetail>(path, (data) => data.hasActiveReply);
  function select(id: string) {
    setSelected(id);
    try {
      sessionStorage.setItem(selectedKey, id);
    } catch {
      /* Current selection remains in memory. */
    }
  }
  function rememberCreation(id: string | null) {
    setPendingCreate(id);
    try {
      if (id) sessionStorage.setItem(creationKey, id);
      else sessionStorage.removeItem(creationKey);
    } catch {
      /* In-memory recovery is still available. */
    }
  }
  async function newConversation() {
    if (creationInFlight.current || sending) return;
    creationInFlight.current = true;
    setCreating(true);
    setCreationError("");
    const requestId = pendingCreate ?? crypto.randomUUID();
    rememberCreation(requestId);
    try {
      const conversation = await request<ConversationRecord>(
        `/findings/${findingId}/conversations`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ clientRequestId: requestId }),
        },
      );
      rememberCreation(null);
      select(conversation.id);
      refresh();
    } catch (error) {
      if (error instanceof ApiError && error.status < 500)
        rememberCreation(null);
      setCreationError(
        error instanceof Error
          ? error.message
          : "Could not start a conversation.",
      );
    } finally {
      creationInFlight.current = false;
      setCreating(false);
    }
  }
  return (
    <div className="conversation-workspace">
      <div className="conversation-toolbar">
        <label>
          Conversation
          <select
            aria-label="Conversation"
            value={selected}
            disabled={!data || creating || sending || !!pendingCreate}
            onChange={(event) => select(event.target.value)}
          >
            {data ? (
              data.conversations.map((conversation, index) => (
                <option key={conversation.id} value={conversation.id}>
                  Conversation {index + 1} ·{" "}
                  {formatDate(conversation.createdAt)}
                </option>
              ))
            ) : (
              <option value={selected}>Loading conversation…</option>
            )}
          </select>
        </label>
        <button
          className="secondary"
          disabled={
            creating ||
            sending ||
            (!pendingCreate && (!data || data.hasActiveReply))
          }
          onClick={() => void newConversation()}
        >
          {creating
            ? "Opening…"
            : pendingCreate
              ? "Check new conversation"
              : "New conversation"}
        </button>
      </div>
      <p className="muted small">
        New conversations start without earlier chat history. Your code, this
        finding, and all previous conversations are kept.
      </p>
      {data?.hasActiveReply && (
        <p className="muted small">
          Wait for this finding’s current reply to finish before starting
          another conversation or question.
        </p>
      )}
      {creationError && (
        <p className="review-error" role="alert">
          {creationError}
        </p>
      )}
      {pendingCreate && !creating && (
        <p className="muted small">
          Creation is not yet confirmed. Check new conversation to recover the
          same conversation without duplicating it.
        </p>
      )}
      {error && selected !== findingId && (
        <button className="text-button" onClick={() => select(findingId)}>
          Open original conversation
        </button>
      )}
      <Conversation
        key={selected}
        findingId={findingId}
        conversationId={selected}
        data={data}
        error={error}
        refresh={refresh}
        onBusyChange={setSending}
        locked={creating || !!pendingCreate}
      />
    </div>
  );
}

function Conversation({
  findingId,
  conversationId,
  data,
  error,
  refresh,
  onBusyChange,
  locked,
}: {
  findingId: string;
  conversationId: string;
  data?: DiscussionDetail;
  error?: string;
  refresh: () => void;
  onBusyChange: (busy: boolean) => void;
  locked: boolean;
}) {
  // Keep original keys for old drafts and pending submissions after the migration.
  const scope =
    conversationId === findingId ? findingId : `${findingId}:${conversationId}`;
  const storageKey = `discussion-pending:${scope}`;
  const [pending, setPending] = useState<Submission | null>(() =>
    readPending(storageKey),
  );
  const [message, setMessage] = useState(() => {
    try {
      return (
        pending?.message ??
        sessionStorage.getItem(`discussion-draft:${scope}`) ??
        ""
      );
    } catch {
      return pending?.message ?? "";
    }
  });
  useEffect(() => {
    try {
      if (message) sessionStorage.setItem(`discussion-draft:${scope}`, message);
      else sessionStorage.removeItem(`discussion-draft:${scope}`);
    } catch {
      /* Draft persistence is best effort when storage is unavailable. */
    }
  }, [scope, message]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const inFlight = useRef(false);
  const composer = useRef<HTMLTextAreaElement>(null);
  const historyList = useRef<HTMLOListElement>(null);
  const path = `/findings/${findingId}/discussion`;
  const active = data?.hasActiveReply ?? false;
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
    if (locked || inFlight.current || (!pending && (active || !message.trim())))
      return;
    inFlight.current = true;
    setBusy(true);
    onBusyChange(true);
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
        body: JSON.stringify({ ...submission, conversationId }),
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
      onBusyChange(false);
    }
  }

  async function retryTurn(turn: DiscussionTurn) {
    if (locked || inFlight.current || active || pending) return;
    inFlight.current = true;
    setBusy(true);
    onBusyChange(true);
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
      onBusyChange(false);
    }
  }

  return (
    <section className="discussion" aria-label="Finding discussion">
      <p className="discussion-help">
        Ask about this finding. OpenAI receives the snippet, finding, and your
        most recent 10 completed exchanges from this conversation only. Replies
        do not change your code.
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
                      disabled={locked || busy || active || !!pending}
                      onClick={() => retryTurn(turn)}
                    >
                      Retry reply
                    </button>
                  ) : (
                    <button
                      className="text-button"
                      disabled={locked || busy || active || !!pending}
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
          <button className="secondary" disabled={locked} onClick={send}>
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
          disabled={locked || busy || active || !!pending || !data}
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
              locked ||
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
