import { StrictMode, useEffect, useRef, useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import {
  HashRouter,
  Link,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { CodeView } from "./CodeView";
import type { Finding } from "./api";
import { ReviewPanel } from "./ReviewPanel";
import { Discussion } from "./Discussion";
import { examples } from "./examples";
import {
  formatDate,
  languageLabel,
  languages,
  request,
  statusLabels,
  useResource,
  type ReviewStatus,
  type ReviewHistory,
  type Snippet,
  type SnippetDetail,
  type SnippetList,
} from "./api";
import "./styles.css";

function Status({ value }: { value: ReviewStatus }) {
  return (
    <span className={`badge status-${value}`}>
      <span aria-hidden="true">●</span> {statusLabels[value]}
    </span>
  );
}
function ErrorPanel({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-panel" role="alert">
      <p>{message}</p>
      {retry && (
        <button className="secondary" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
function Dashboard() {
  const [params, setParams] = useSearchParams();
  const language = params.get("language") ?? "";
  const status = params.get("reviewStatus") ?? "";
  const query = new URLSearchParams();
  if (language) query.set("language", language);
  if (status) query.set("reviewStatus", status);
  const { data, error, retry } = useResource<SnippetList>(
    `/snippets?${query}`,
    (data) =>
      data.snippets.some((snippet) => snippet.reviewStatus === "in_progress"),
  );
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }
  const availableLanguages = Array.from(
    new Set([...(data?.languages ?? []), ...(language ? [language] : [])]),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR WORKSPACE</p>
          <h1>Code snippets</h1>
          <p className="muted">
            Small pieces of code. A clearer place to review them.
          </p>
        </div>
        <Link className="button primary" to="/new">
          ＋ New snippet
        </Link>
      </div>
      <section className="panel">
        <div className="toolbar">
          <div className="filters">
            <label>
              Language
              <select
                value={language}
                onChange={(event) => filter("language", event.target.value)}
              >
                <option value="">All languages</option>
                {availableLanguages.map((value) => (
                  <option key={value} value={value}>
                    {languageLabel(value)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Review status
              <select
                value={status}
                onChange={(event) => filter("reviewStatus", event.target.value)}
              >
                <option value="">All statuses</option>
                {Object.entries(statusLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            {(language || status) && (
              <button className="text-button" onClick={() => setParams({})}>
                Clear filters
              </button>
            )}
          </div>
          <span className="muted small" aria-live="polite">
            {data
              ? `${data.snippets.length} snippet${data.snippets.length === 1 ? "" : "s"}`
              : "Loading…"}
          </span>
        </div>
        {error ? (
          <ErrorPanel message={error} retry={retry} />
        ) : !data ? (
          <p className="loading" role="status">
            Loading snippets…
          </p>
        ) : data.snippets.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Snippet</th>
                  <th>Language</th>
                  <th>Created</th>
                  <th>Review status</th>
                </tr>
              </thead>
              <tbody>
                {data.snippets.map((snippet) => (
                  <tr key={snippet.id}>
                    <td>
                      <Link
                        className="snippet-link"
                        to={`/snippets/${snippet.id}`}
                      >
                        {snippet.title}
                      </Link>
                    </td>
                    <td>
                      <span className="language-tag">
                        {languageLabel(snippet.language)}
                      </span>
                    </td>
                    <td className="date">
                      <time dateTime={snippet.createdAt}>
                        {formatDate(snippet.createdAt)}
                      </time>
                    </td>
                    <td>
                      <Status value={snippet.reviewStatus} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty">
            <span className="empty-symbol" aria-hidden="true">
              {"{ }"}
            </span>
            <h2>
              {language || status
                ? "No matching snippets"
                : "Your first snippet starts here"}
            </h2>
            <p className="muted">
              {language || status
                ? "Try a different language or review status."
                : "Save a function, a query, or a small piece of code."}
            </p>
            {language || status ? (
              <button className="secondary" onClick={() => setParams({})}>
                Clear filters
              </button>
            ) : (
              <Link className="button primary" to="/new">
                Create a snippet
              </Link>
            )}
          </div>
        )}
      </section>
    </>
  );
}
function NewSnippet() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState("");
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    setError("");
    if (!title.trim() || !code.trim()) {
      setError("Enter a title and some code before saving.");
      return;
    }
    if (Array.from(code).length > 100_000) {
      setError("Code must be no more than 100,000 characters.");
      return;
    }
    submitting.current = true;
    setSaving(true);
    try {
      const snippet = await request<Snippet>("/snippets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, language, code }),
      });
      navigate(`/snippets/${snippet.id}`);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Could not save this snippet.",
      );
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  }
  return (
    <>
      <Link className="back-link" to="/">
        ← All snippets
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ADD TO YOUR WORKSPACE</p>
          <h1>New snippet</h1>
          <p className="muted">
            Give your code a title so you can find it later.
          </p>
        </div>
      </div>
      <section className="example-picker" aria-label="Example snippets">
        <label htmlFor="example">Start with an example</label>
        <select
          id="example"
          defaultValue=""
          onChange={(event) => {
            const example = examples.find(
              (item) => item.id === event.target.value,
            );
            if (example) {
              setTitle(example.title);
              setLanguage(example.language);
              setCode(example.code);
            }
            event.target.value = "";
          }}
          disabled={!!title || !!code || saving}
        >
          <option value="">Choose sample code…</option>
          {examples.map((example) => (
            <option key={example.id} value={example.id}>
              {example.label}
            </option>
          ))}
        </select>
        <p className="muted small">
          Examples fill an empty form. Save and request a review when ready; no
          AI call starts automatically.
        </p>
      </section>
      <form className="panel snippet-form" onSubmit={submit}>
        <fieldset disabled={saving}>
          <div className="form-row">
            <label>
              Title
              <input
                autoFocus
                required
                maxLength={120}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="e.g. Payment retry handler"
              />
            </label>
            <label>
              Language
              <select
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
              >
                {languages.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="code-label">
            Code
            <textarea
              required
              value={code}
              onChange={(event) => setCode(event.target.value)}
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              placeholder="Paste your code here…"
              aria-describedby="code-help"
            />
          </label>
          <div id="code-help" className="form-help">
            <span>
              Saved snippets are read-only. Create a new snippet for a revision.
            </span>
            <span>{Array.from(code).length.toLocaleString()} / 100,000</span>
          </div>
        </fieldset>
        {error && <ErrorPanel message={error} />}
        <div className="form-actions">
          <Link className="button secondary" to="/">
            Cancel
          </Link>
          <button className="primary" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save snippet"}
          </button>
        </div>
      </form>
    </>
  );
}
function Detail() {
  const { id } = useParams();
  const [selection, setSelection] = useState<Finding | null>(null);
  const [discussed, setDiscussed] = useState<Finding | null>(null);
  const discussionRegion = useRef<HTMLElement>(null);
  const [params, setParams] = useSearchParams();
  const chosenReviewId = params.get("review");
  const history = useResource<ReviewHistory>(
    `/snippets/${encodeURIComponent(id ?? "")}/reviews`,
    (data) =>
      data.reviews.some(
        (run) => run.status === "queued" || run.status === "running",
      ),
  );
  useEffect(() => {
    if (discussed) {
      discussionRegion.current?.scrollIntoView({
        block: "start",
        behavior: "instant",
      });
      discussionRegion.current?.focus({ preventScroll: true });
    }
  }, [discussed]);
  const { data, error, retry } = useResource<SnippetDetail>(
    `/snippets/${encodeURIComponent(id ?? "")}`,
    (data) =>
      data.latestReview?.status === "queued" ||
      data.latestReview?.status === "running",
  );
  if (error)
    return (
      <>
        <Link className="back-link" to="/">
          ← All snippets
        </Link>
        <ErrorPanel message={error} retry={retry} />
      </>
    );
  if (!data)
    return (
      <p className="loading" role="status">
        Loading snippet…
      </p>
    );
  const { snippet, latestReview } = data;
  const viewedReview = chosenReviewId
    ? (history.data?.reviews.find((run) => run.id === chosenReviewId) ?? null)
    : latestReview;
  const selectedFinding =
    selection?.reviewRunId === viewedReview?.id ? selection : null;
  const discussionFinding =
    discussed?.reviewRunId === viewedReview?.id ? discussed : null;
  if (chosenReviewId && !history.data)
    return (
      <ErrorPanel
        message={history.error ?? "Loading review history…"}
        retry={history.retry}
      />
    );
  if (chosenReviewId && !viewedReview)
    return (
      <ErrorPanel
        message="This review is not in this snippet’s history."
        retry={() => setParams({})}
      />
    );
  const status: ReviewStatus = !latestReview
    ? "not_reviewed"
    : latestReview.status === "succeeded"
      ? "reviewed"
      : latestReview.status === "failed"
        ? "failed"
        : "in_progress";
  return (
    <>
      <Link className="back-link" to="/">
        ← All snippets
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">SNIPPET</p>
          <h1 className="snippet-title">{snippet.title}</h1>
          <div className="metadata">
            <span className="language-tag">
              {languageLabel(snippet.language)}
            </span>
            <span>
              Created{" "}
              <time dateTime={snippet.createdAt}>
                {formatDate(snippet.createdAt)}
              </time>
            </span>
          </div>
        </div>
        <Status value={status} />
      </div>
      <div className="history-toolbar">
        <label htmlFor="review-history">Review history</label>
        <select
          id="review-history"
          value={chosenReviewId ?? ""}
          disabled={!history.data}
          onChange={(event) => {
            setParams(event.target.value ? { review: event.target.value } : {});
            setSelection(null);
            setDiscussed(null);
          }}
        >
          <option value="">
            Latest review
            {latestReview ? ` · ${latestReview.status}` : " · none yet"}
          </option>
          {history.data?.reviews.map((run, index) => (
            <option key={run.id} value={run.id}>
              Review {history.data!.reviews.length - index} ·{" "}
              {formatDate(run.createdAt)} · {run.status}
            </option>
          ))}
        </select>
        {history.error && (
          <button className="text-button" onClick={history.retry}>
            Retry loading history
          </button>
        )}
        {chosenReviewId && chosenReviewId !== latestReview?.id && (
          <span className="history-notice">
            Viewing an earlier review. Code is unchanged.
          </span>
        )}
      </div>
      <div className="detail-grid">
        <section className="panel code-panel" aria-label="Code">
          <div className="section-heading">
            <h2>Source code</h2>
            <span className="muted small">
              {snippet.code.replace(/\r\n|\r/g, "\n").split("\n").length} lines
              · Read-only
            </span>
          </div>
          <CodeView
            code={snippet.code}
            language={snippet.language}
            selection={selectedFinding}
          />
          {selectedFinding && (
            <div className="code-selection-label" role="status">
              Lines {selectedFinding.startLine}–{selectedFinding.endLine}{" "}
              selected
              <button
                className="text-button"
                onClick={() => setSelection(null)}
              >
                Clear highlight
              </button>
            </div>
          )}
        </section>
        <ReviewPanel
          key={viewedReview?.id ?? "new"}
          reviewRun={viewedReview}
          discussionFindingId={discussionFinding?.id}
          onDiscuss={(finding) => setDiscussed({ ...finding })}
          snippetId={snippet.id}
          latestReview={latestReview}
          onStarted={() => {
            setParams({});
            setDiscussed(null);
            retry();
            history.retry();
          }}
          selectedFindingId={selectedFinding?.id}
          onSelectFinding={(finding) => setSelection({ ...finding })}
        />
      </div>
      <section
        id="discussion-workspace"
        className="panel discussion-workspace"
        aria-label="Discussion workspace"
        ref={discussionRegion}
        tabIndex={-1}
        hidden={!discussionFinding}
      >
        {discussionFinding && (
          <>
            <div className="discussion-context">
              <p className="eyebrow">FINDING DISCUSSION</p>
              <h2>Let’s look closer</h2>
              <p className="muted">
                Lines {discussionFinding.startLine}–{discussionFinding.endLine}{" "}
                · {discussionFinding.category}
              </p>
              <p>{discussionFinding.description}</p>
              <button
                className="text-button"
                onClick={() => {
                  setDiscussed(null);
                  document
                    .getElementById(`discuss-${discussionFinding.id}`)
                    ?.focus();
                }}
              >
                Close discussion
              </button>
            </div>
            <Discussion
              key={discussionFinding.id}
              findingId={discussionFinding.id}
            />
          </>
        )}
      </section>
    </>
  );
}
function App() {
  return (
    <HashRouter>
      <header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            {"{ }"}
          </span>{" "}
          Snippet Reviewer
        </Link>
        <span className="workspace-label">Local workspace</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewSnippet />} />
          <Route path="/snippets/:id" element={<Detail />} />
          <Route
            path="*"
            element={
              <>
                <h1>Page not found</h1>
                <Link to="/">Return to snippets</Link>
              </>
            }
          />
        </Routes>
      </main>
      <footer>
        Code stays in your local workspace until you request an AI review or
        reply.
      </footer>
    </HashRouter>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
