import { StrictMode, useRef, useState, type FormEvent } from "react";
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
import {
  formatDate,
  languageLabel,
  languages,
  request,
  statusLabels,
  useResource,
  type ReviewStatus,
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
  const { data, error, retry } = useResource<SnippetList>(`/snippets?${query}`);
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
  const { data, error, retry } = useResource<SnippetDetail>(
    `/snippets/${encodeURIComponent(id ?? "")}`,
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
      <div className="detail-grid">
        <section className="panel code-panel" aria-label="Code">
          <div className="section-heading">
            <h2>Source code</h2>
            <span className="muted small">
              {snippet.code.replace(/\r\n|\r/g, "\n").split("\n").length} lines
              · Read-only
            </span>
          </div>
          <CodeView code={snippet.code} language={snippet.language} />
        </section>
        <aside className="panel review-panel">
          <p className="eyebrow">REVIEW</p>
          <h2>{latestReview ? "Review status" : "No review yet"}</h2>
          <p className="muted">
            Your snippet is saved. AI reviews and finding interactions are
            coming in the next step.
          </p>
          {latestReview?.error && (
            <p role="alert" className="review-error">
              {latestReview.error}
            </p>
          )}
        </aside>
      </div>
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
        Code stays in your local workspace until you request an AI review.
      </footer>
    </HashRouter>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
