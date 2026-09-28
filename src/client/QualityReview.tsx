import { useEffect, useId, useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { z } from "zod";
import type { components } from "../shared/api-types";
import { request, useResource, formatDate } from "./api";
import { CodeView } from "./CodeView";

type Catalog = components["schemas"]["Catalog"];
type Session = components["schemas"]["SessionDetail"];
type Case = components["schemas"]["QualityCase"];
type Annotation = components["schemas"]["AnnotationInput"];
type Saved = components["schemas"]["SavedAnnotation"];
type FindingMark = components["schemas"]["FindingAnnotation"];
type Coverage = components["schemas"]["CoverageAnnotation"];
const rating = z.enum([
  "pending",
  "good",
  "problem",
  "uncertain",
  "not_applicable",
]);
const draftSchema = z.object({
  revision: z.number().int().nonnegative(),
  status: z.enum(["draft", "completed"]),
  independentVerdict: z
    .enum(["pending", "issue_found", "no_issue", "uncertain"])
    .default("pending"),
  contractClarity: z
    .enum(["pending", "sufficient", "missing", "uncertain"])
    .default("pending"),
  referenceReason: z
    .enum([
      "pending",
      "supported",
      "false_positive",
      "missing_issue",
      "wrong_details",
      "missing_context",
      "needs_verification",
    ])
    .default("pending"),
  independentNotes: z.string(),
  contractNotes: z.string(),
  referenceVerdict: z.enum([
    "pending",
    "approved",
    "needs_changes",
    "uncertain",
  ]),
  referenceNotes: z.string(),
  proposedReference: z.string(),
  findings: z.array(
    z.object({
      runIndex: z.number(),
      findingIndex: z.number(),
      verdict: z.enum([
        "pending",
        "correct",
        "incorrect",
        "uncertain",
        "duplicate",
      ]),
      reason: z
        .enum([
          "pending",
          "supported",
          "unsupported_assumption",
          "contradicts_code",
          "not_actionable",
          "duplicate",
          "missing_context",
          "needs_verification",
        ])
        .default("pending"),
      location: rating,
      severity: rating,
      fix: rating,
      notes: z.string(),
    }),
  ),
  coverage: z.array(
    z.object({
      runIndex: z.number(),
      verdict: z.enum(["pending", "complete", "missed", "uncertain", "failed"]),
      notes: z.string(),
    }),
  ),
});
const referenceReasons: Record<
  string,
  [NonNullable<Annotation["referenceReason"]>, string][]
> = {
  approved: [["supported", "The code supports this reference"]],
  needs_changes: [
    ["false_positive", "Flags a problem that is not real"],
    ["missing_issue", "Misses a real issue"],
    ["wrong_details", "Lines, severity or explanation need correction"],
  ],
  uncertain: [
    ["missing_context", "Need the intended inputs / behavior"],
    ["needs_verification", "Need help verifying this"],
  ],
};
const findingReasons: Record<
  string,
  [NonNullable<FindingMark["reason"]>, string][]
> = {
  correct: [["supported", "The code supports this finding"]],
  incorrect: [
    ["unsupported_assumption", "Assumes requirements that were not given"],
    ["contradicts_code", "The described behavior does not match the code"],
    ["not_actionable", "Only a preference, not an actionable problem"],
  ],
  duplicate: [["duplicate", "Repeats another finding in this run"]],
  uncertain: [
    ["missing_context", "Need more context to judge"],
    ["needs_verification", "Need help verifying this"],
  ],
};
function Choices({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  const name = useId();
  return (
    <fieldset className="quality-choices">
      <legend>{label}</legend>
      <div>
        {options.map(([key, text]) => (
          <label key={key} className={value === key ? "choice-selected" : ""}>
            <input
              type="radio"
              name={name}
              value={key}
              checked={value === key}
              onChange={() => onChange(key)}
            />
            {text}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
function initial(caseData: Case, saved?: Saved): Annotation {
  const empty: Annotation = {
    revision: 0,
    status: "draft",
    independentVerdict: "pending",
    contractClarity: "pending",
    referenceReason: "pending",
    independentNotes: "",
    contractNotes: "",
    referenceVerdict: "pending",
    referenceNotes: "",
    proposedReference: "",
    findings: caseData.runs.flatMap((run) =>
      run.findings.map((finding, index) => ({
        runIndex: run.index,
        findingIndex: index,
        verdict: "pending",
        reason: "pending",
        location: "pending",
        severity: "pending",
        fix: finding.suggestedFix ? "pending" : "not_applicable",
        notes: "",
      })),
    ),
    coverage: caseData.runs.map((run) => ({
      runIndex: run.index,
      verdict: run.status === "failed" ? "failed" : "pending",
      notes: "",
    })),
  };
  if (!saved) return empty;
  const { savedAt: _, ...annotation } = saved;
  // Draft API writes may omit assessments; restore all source rows as pending.
  return {
    ...empty,
    ...annotation,
    findings: empty.findings!.map((item) => ({
      ...item,
      ...saved.findings?.find(
        (candidate) =>
          candidate.runIndex === item.runIndex &&
          candidate.findingIndex === item.findingIndex,
      ),
    })),
    coverage: empty.coverage!.map((item) => ({
      ...item,
      ...saved.coverage?.find(
        (candidate) => candidate.runIndex === item.runIndex,
      ),
    })),
  };
}
function download(name: string, content: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(content, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function QualityHome() {
  const resource = useResource<Catalog>("/quality/catalog");
  const navigate = useNavigate();
  const [source, setSource] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <>
      <Link to="/" className="back-link">
        ← All snippets
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">EVALUATION WORKSPACE</p>
          <h1>Human review</h1>
          <p className="muted">
            Choose your answers, then save. Notes are optional throughout; no
            new AI calls.
          </p>
        </div>
      </div>
      <section className="panel quality-intro">
        <h2>Your first review</h2>
        <ol>
          <li>
            Read the code and select your assessment before revealing the
            reference. No written explanation is required.
          </li>
          <li>
            Confirm or challenge the proposed reference. Missing requirements
            can mean “Uncertain”.
          </li>
          <li>
            Judge each finding, check for missed issues, then save and continue.
          </li>
        </ol>
        <p className="muted">
          These are development cases used to tune the prompt. Completing
          annotations does not make them an independent test set or
          automatically approve them as ground truth.
        </p>
      </section>
      {(error || resource.error) && (
        <p className="error-panel" role="alert">
          {error || resource.error}{" "}
          <button onClick={resource.retry}>Reload</button>
        </p>
      )}
      {!resource.data ? (
        <p role="status">Loading evaluations…</p>
      ) : (
        <>
          <form
            className="panel quality-intro"
            onSubmit={async (event) => {
              event.preventDefault();
              if (busy) return;
              setBusy(true);
              setError("");
              try {
                const session = await request<Session>("/quality/sessions", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    sourceId: source || resource.data!.sources[0]?.id,
                    reviewer,
                  }),
                });
                navigate(`/quality/${session.id}`);
              } catch (error) {
                setError(
                  error instanceof Error
                    ? error.message
                    : "Could not start review",
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            <fieldset disabled={busy}>
              <div className="quality-fields">
                <label>
                  Evaluation results
                  <select
                    value={source || resource.data.sources[0]?.id || ""}
                    onChange={(e) => setSource(e.target.value)}
                  >
                    {resource.data.sources.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label} · {item.promptVersion} · {item.caseCount}{" "}
                        cases / {item.runCount} runs
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Reviewer name
                  <input
                    required
                    maxLength={80}
                    value={reviewer}
                    onChange={(e) => setReviewer(e.target.value)}
                    placeholder="Your name"
                  />
                </label>
              </div>
              <button
                className="primary"
                disabled={!reviewer.trim() || !resource.data.sources.length}
              >
                {busy ? "Opening…" : "Start / resume review"}
              </button>
              <p className="muted small">
                The same name and results resume the same session. Another
                reviewer can create an independent session.
              </p>
            </fieldset>
          </form>
          {resource.data.sessions.length > 0 && (
            <section className="panel quality-intro">
              <h2>Saved sessions</h2>
              <ul className="quality-sessions">
                {resource.data.sessions.map((session) => (
                  <li key={session.id}>
                    <Link to={`/quality/${session.id}`}>
                      {session.reviewer} · {session.label}
                    </Link>
                    <span className="muted">
                      {session.completed}/{session.total} completed ·{" "}
                      {formatDate(session.createdAt)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {!!resource.data.unavailable.length && (
            <p className="muted small">
              Unavailable sources (missing or mismatched dataset snapshot):{" "}
              {resource.data.unavailable.join(", ")}. Existing saved sessions
              remain available.
            </p>
          )}
        </>
      )}
    </>
  );
}

export function QualitySession() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const resource = useResource<Session>(
    `/quality/sessions/${encodeURIComponent(id ?? "")}`,
  );
  if (resource.error)
    return (
      <p className="error-panel" role="alert">
        {resource.error} <button onClick={resource.retry}>Retry</button>{" "}
        <Link to="/quality">Back to human review</Link>
      </p>
    );
  if (!resource.data) return <p role="status">Loading annotation session…</p>;
  const session = resource.data;
  const caseData =
    session.cases.find((item) => item.id === params.get("case")) ??
    session.cases[0];
  if (!caseData) return <p role="alert">This session has no cases.</p>;
  const position = session.cases.indexOf(caseData);
  const completed = Object.values(session.annotations).filter(
    (item) => item.status === "completed",
  ).length;
  return (
    <>
      <Link to="/quality" className="back-link">
        ← Human review sessions
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            {session.source.promptVersion} · {session.source.model}
          </p>
          <h1>Review with evidence</h1>
          <p className="muted">
            {session.reviewer} · {completed}/{session.cases.length} cases
            completed · Development set
          </p>
        </div>
        <a
          className="button secondary"
          href={`/api/quality/sessions/${session.id}/export`}
          download
        >
          Export saved annotations
        </a>
      </div>
      <p className="muted small quality-export-note">
        Export includes original code, results, reference labels and every saved
        revision. Unsaved browser drafts are excluded. No labels are
        automatically promoted to the reference dataset.
      </p>
      <div className="quality-layout">
        <nav className="panel quality-case-list" aria-label="Evaluation cases">
          {session.cases.map((item, index) => (
            <button
              key={item.id}
              className={caseData.id === item.id ? "case-active" : ""}
              aria-current={caseData.id === item.id ? "step" : undefined}
              onClick={() => setParams({ case: item.id })}
            >
              <span>
                {index + 1}. {item.id}
              </span>
              <small>
                {session.annotations[item.id]?.status ?? "Not started"}
              </small>
            </button>
          ))}
        </nav>
        <CaseEditor
          key={`${session.id}:${caseData.id}`}
          session={session}
          caseData={caseData}
          saved={session.annotations[caseData.id]}
          onSaved={(saved) =>
            resource.update((data) => ({
              ...data,
              annotations: { ...data.annotations, [caseData.id]: saved },
            }))
          }
          onNext={
            position < session.cases.length - 1
              ? () => setParams({ case: session.cases[position + 1]!.id })
              : undefined
          }
        />
      </div>
    </>
  );
}

function Score({
  label,
  value,
  onChange,
}: {
  label: string;
  value: FindingMark["location"];
  onChange: (value: FindingMark["location"]) => void;
}) {
  return (
    <label>
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as FindingMark["location"])}
      >
        <option value="pending">Choose…</option>
        <option value="good">Good</option>
        <option value="problem">Problem</option>
        <option value="uncertain">Uncertain</option>
        <option value="not_applicable">Not applicable</option>
      </select>
    </label>
  );
}
function CaseEditor({
  session,
  caseData,
  saved,
  onSaved,
  onNext,
}: {
  session: Session;
  caseData: Case;
  saved?: Saved;
  onSaved: (saved: Saved) => void;
  onNext?: () => void;
}) {
  const storageKey = `human-review:${session.id}:${caseData.id}`;
  const base = useRef(initial(caseData, saved));
  const [draft, setDraft] = useState<Annotation>(() => {
    try {
      const parsed = draftSchema.safeParse(
        JSON.parse(sessionStorage.getItem(storageKey) ?? "null"),
      );
      if (parsed.success)
        return initial(caseData, { ...parsed.data, savedAt: "" });
    } catch {
      /* Server state remains usable if browser storage is unavailable. */
    }
    return base.current;
  });
  const [showReference, setShowReference] = useState(
    !!draft.referenceVerdict && draft.referenceVerdict !== "pending",
  );
  const [showOutput, setShowOutput] = useState(
    saved?.status === "completed" ||
      draft.findings?.some((finding) => finding.verdict !== "pending") ||
      false,
  );
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [storageError, setStorageError] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(base.current);
  const stale = draft.revision !== base.current.revision;
  useEffect(() => {
    try {
      if (dirty) sessionStorage.setItem(storageKey, JSON.stringify(draft));
      else sessionStorage.removeItem(storageKey);
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  }, [draft, dirty, storageKey]);
  useEffect(() => {
    function warn(event: BeforeUnloadEvent) {
      if (dirty) event.preventDefault();
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function change(patch: Partial<Annotation>) {
    setDraft((previous) => ({ ...previous, ...patch, status: "draft" }));
    setMessage("");
  }
  function markFinding(
    runIndex: number,
    findingIndex: number,
    patch: Partial<FindingMark>,
  ) {
    change({
      findings: draft.findings!.map((f) =>
        f.runIndex === runIndex && f.findingIndex === findingIndex
          ? { ...f, ...patch }
          : f,
      ),
    });
  }
  function markCoverage(runIndex: number, patch: Partial<Coverage>) {
    change({
      coverage: draft.coverage!.map((item) =>
        item.runIndex === runIndex ? { ...item, ...patch } : item,
      ),
    });
  }
  async function save(status: "draft" | "completed", next = false) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await request<Saved>(
        `/quality/sessions/${session.id}/cases/${encodeURIComponent(caseData.id)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...draft, status }),
        },
      );
      base.current = initial(caseData, result);
      setDraft(base.current);
      onSaved(result);
      // Remove the previous draft before navigation can unmount this editor.
      try {
        sessionStorage.removeItem(storageKey);
      } catch {
        /* Explicit save succeeded. */
      }
      setMessage(
        `Saved ${status === "completed" ? "completed assessment" : "draft"} · revision ${result.revision}`,
      );
      if (next) onNext?.();
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not save. Your draft is retained.",
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  return (
    <article className="quality-editor">
      <section className="panel">
        <div className="section-heading">
          <h2>{caseData.id}</h2>
          <span className="language-tag">{caseData.language}</span>
        </div>
        <CodeView code={caseData.code} language={caseData.language} />
      </section>
      <fieldset disabled={busy}>
        <section className="panel quality-intro">
          <h2>1. Your independent assessment</h2>
          <p className="muted small">
            The model saw the code and language, plus the review prompt.
            Reference notes below were not part of its input. Do not grade
            against hidden requirements.
          </p>
          <Choices
            label="What do you think of this code?"
            value={draft.independentVerdict ?? "pending"}
            options={[
              ["issue_found", "I see a potential issue"],
              ["no_issue", "I don't see an issue"],
              ["uncertain", "I'm not sure yet"],
            ]}
            onChange={(value) =>
              change({
                independentVerdict: value as Annotation["independentVerdict"],
              })
            }
          />
          <Choices
            label="Are the intended inputs and behavior clear enough?"
            value={draft.contractClarity ?? "pending"}
            options={[
              ["sufficient", "Enough context to judge"],
              ["missing", "Important requirements are missing"],
              ["uncertain", "I'm not sure"],
            ]}
            onChange={(value) =>
              change({
                contractClarity: value as Annotation["contractClarity"],
              })
            }
          />
          <details
            className="quality-optional"
            open={!!(draft.independentNotes || draft.contractNotes)}
          >
            <summary>Optional code notes</summary>
            <label>
              Your observations and evidence
              <textarea
                maxLength={8000}
                rows={3}
                value={draft.independentNotes}
                onChange={(e) => change({ independentNotes: e.target.value })}
                placeholder="What happens, on which lines? Give a minimal input and result, or explain why the code is sound."
              />
            </label>
            <label>
              Input / behavior assumptions
              <textarea
                maxLength={8000}
                rows={3}
                value={draft.contractNotes}
                onChange={(e) => change({ contractNotes: e.target.value })}
                placeholder="Which requirements are explicit? Which are unknown? An exception alone does not prove a bug."
              />
            </label>
          </details>
          {!showReference && (
            <button
              className="secondary"
              disabled={
                ((draft.independentVerdict ?? "pending") === "pending" &&
                  !draft.independentNotes?.trim()) ||
                ((draft.contractClarity ?? "pending") === "pending" &&
                  !draft.contractNotes?.trim())
              }
              onClick={() => setShowReference(true)}
            >
              Reveal proposed reference
            </button>
          )}
        </section>
        {showReference && (
          <section className="panel quality-intro">
            <h2>2. Validate the proposed reference</h2>
            <p className="muted small">
              AI-authored development labels. Challenge them when evidence or
              requirements are missing.
            </p>
            {caseData.expected.length ? (
              caseData.expected.map((expected, index) => (
                <div className="quality-reference" key={index}>
                  <strong>
                    {String(expected.id)} · lines {String(expected.startLine)}–
                    {String(expected.endLine)}
                  </strong>
                  <p>{String(expected.description)}</p>
                  <p className="muted small">
                    {String(expected.category)} ·{" "}
                    {Array.isArray(expected.severities)
                      ? expected.severities.join(" / ")
                      : ""}
                  </p>
                </div>
              ))
            ) : (
              <p className="quality-reference">
                Proposed reference: no actionable issues.
              </p>
            )}
            {caseData.notes && (
              <p className="muted">
                Reference author’s notes (not sent to the model):{" "}
                {caseData.notes}
              </p>
            )}
            <label>
              Reference verdict
              <select
                value={draft.referenceVerdict}
                onChange={(e) =>
                  change({
                    referenceVerdict: e.target
                      .value as Annotation["referenceVerdict"],
                    referenceReason: "pending",
                  })
                }
              >
                <option value="pending">Choose…</option>
                <option value="approved">
                  Approved — supported by the visible context
                </option>
                <option value="needs_changes">Needs changes</option>
                <option value="uncertain">
                  Uncertain — missing context / evidence
                </option>
              </select>
            </label>
            {draft.referenceVerdict !== "pending" && (
              <Choices
                label="Why this reference verdict?"
                value={draft.referenceReason ?? "pending"}
                options={
                  referenceReasons[draft.referenceVerdict ?? "pending"] ?? []
                }
                onChange={(value) =>
                  change({
                    referenceReason: value as Annotation["referenceReason"],
                  })
                }
              />
            )}
            {draft.referenceVerdict === "needs_changes" && (
              <p className="muted small">
                You can flag this for correction without writing a replacement
                answer. We can discuss the details later.
              </p>
            )}
            <details
              className="quality-optional"
              open={!!(draft.referenceNotes || draft.proposedReference)}
            >
              <summary>Optional reference notes</summary>
              <label>
                Reference reasoning
                <textarea
                  maxLength={8000}
                  rows={3}
                  value={draft.referenceNotes}
                  onChange={(e) => change({ referenceNotes: e.target.value })}
                  placeholder="Why is the proposed reference justified, wrong, or uncertain?"
                />
              </label>
              <label>
                Proposed reference changes
                <textarea
                  maxLength={8000}
                  rows={3}
                  value={draft.proposedReference}
                  onChange={(e) =>
                    change({ proposedReference: e.target.value })
                  }
                  placeholder="Optional. You can flag a correction now and discuss the details later. Describe issues, lines, impact and valid fix directions; use 'No issues' if appropriate. Changes requiring a new input contract need a new eval run."
                />
              </label>
            </details>
            {!showOutput && (
              <button
                className="secondary"
                disabled={
                  draft.referenceVerdict === "pending" ||
                  ((draft.referenceReason ?? "pending") === "pending" &&
                    !draft.referenceNotes?.trim())
                }
                onClick={() => setShowOutput(true)}
              >
                Reveal model outputs
              </button>
            )}
          </section>
        )}
        {showReference && showOutput && (
          <section className="panel quality-intro">
            <h2>3. Assess the model outputs</h2>
            <p className="muted small">
              Correct = a real supported issue; Incorrect = a false claim;
              Uncertain = insufficient context; Duplicate = the same issue
              repeated in this run. Judge fix behavior, not wording. Repeated
              runs are independent outputs.
            </p>
            {caseData.runs.map((run) => (
              <section
                className="quality-run"
                key={run.index}
                aria-label={`Run ${run.repeat}`}
              >
                <h3>
                  Run {run.repeat} · {run.status}
                </h3>
                {run.status === "failed" ? (
                  <p role="note">
                    Provider call failed ({run.errorType}). This is not a clean
                    review and cannot count as “no issues”.
                  </p>
                ) : !run.findings.length ? (
                  <p>
                    No findings returned. Check whether this is correct or
                    whether an issue was missed.
                  </p>
                ) : (
                  run.findings.map((finding, index) => {
                    const mark = draft.findings!.find(
                      (item) =>
                        item.runIndex === run.index &&
                        item.findingIndex === index,
                    )!;
                    return (
                      <section
                        key={index}
                        className="quality-finding"
                        aria-label={`Finding ${index + 1}`}
                      >
                        <h4>
                          Finding {index + 1} · lines {finding.startLine}–
                          {finding.endLine} · {finding.severity} ·{" "}
                          {finding.category}
                        </h4>
                        <p className="quality-prose">{finding.description}</p>
                        <details>
                          <summary>Suggested fix</summary>
                          <pre className="quality-fix">
                            {finding.suggestedFix || "No fix suggested."}
                          </pre>
                        </details>
                        <label>
                          Finding verdict
                          <select
                            value={mark.verdict}
                            onChange={(e) =>
                              markFinding(run.index, index, {
                                verdict: e.target
                                  .value as FindingMark["verdict"],
                                reason: "pending",
                              })
                            }
                          >
                            <option value="pending">Choose…</option>
                            <option value="correct">Correct</option>
                            <option value="incorrect">Incorrect</option>
                            <option value="uncertain">Uncertain</option>
                            <option value="duplicate">Duplicate</option>
                          </select>
                        </label>
                        <div className="quality-fields">
                          <Score
                            label="Line location"
                            value={mark.location}
                            onChange={(location) =>
                              markFinding(run.index, index, { location })
                            }
                          />
                          <Score
                            label="Severity"
                            value={mark.severity}
                            onChange={(severity) =>
                              markFinding(run.index, index, { severity })
                            }
                          />
                          <Score
                            label="Fix quality"
                            value={mark.fix}
                            onChange={(fix) =>
                              markFinding(run.index, index, { fix })
                            }
                          />
                        </div>
                        {mark.verdict !== "pending" && (
                          <Choices
                            label="Why this finding verdict?"
                            value={mark.reason ?? "pending"}
                            options={
                              findingReasons[mark.verdict ?? "pending"] ?? []
                            }
                            onChange={(value) =>
                              markFinding(run.index, index, {
                                reason: value as FindingMark["reason"],
                              })
                            }
                          />
                        )}
                        <details
                          className="quality-optional"
                          open={!!mark.notes}
                        >
                          <summary>Optional finding notes</summary>
                          <label>
                            Finding evidence
                            <textarea
                              maxLength={8000}
                              rows={3}
                              value={mark.notes}
                              onChange={(e) =>
                                markFinding(run.index, index, {
                                  notes: e.target.value,
                                })
                              }
                              placeholder="Explain the verdict and rating problems. Note valid extra issues missing from the reference."
                            />
                          </label>
                        </details>
                      </section>
                    );
                  })
                )}
                <label>
                  Coverage verdict
                  <select
                    value={
                      draft.coverage!.find(
                        (item) => item.runIndex === run.index,
                      )!.verdict
                    }
                    onChange={(e) =>
                      markCoverage(run.index, {
                        verdict: e.target.value as Coverage["verdict"],
                      })
                    }
                  >
                    <option value="pending">Choose…</option>
                    {run.status === "failed" ? (
                      <option value="failed">
                        Failed call — cannot assess coverage
                      </option>
                    ) : (
                      <>
                        <option value="complete">
                          No supported issues missed
                        </option>
                        <option value="missed">
                          One or more issues missed
                        </option>
                        <option value="uncertain">Uncertain</option>
                      </>
                    )}
                  </select>
                </label>
                <details
                  className="quality-optional"
                  open={
                    !!draft.coverage!.find(
                      (item) => item.runIndex === run.index,
                    )!.notes
                  }
                >
                  <summary>Optional coverage notes</summary>
                  <label>
                    Coverage evidence / missed issues
                    <textarea
                      maxLength={8000}
                      rows={3}
                      value={
                        draft.coverage!.find(
                          (item) => item.runIndex === run.index,
                        )!.notes
                      }
                      onChange={(e) =>
                        markCoverage(run.index, { notes: e.target.value })
                      }
                      placeholder="Name any missed issues and affected lines; explain a clean review or uncertainty. Check all issues, including proposed reference changes."
                    />
                  </label>
                </details>
              </section>
            ))}
          </section>
        )}
      </fieldset>
      <section className="panel quality-save" aria-label="Save assessment">
        <p role="status">
          {message ||
            (dirty
              ? "Unsaved changes — browser draft retained in this tab"
              : saved
                ? `Saved ${saved.status} · revision ${saved.revision}`
                : "Not saved yet")}
        </p>
        {storageError && (
          <p role="alert">
            Browser draft storage is unavailable. Save before leaving this case.
          </p>
        )}
        {stale && (
          <p role="alert">
            Your recovered draft is based on an older revision. Download it
            before loading the saved version.
          </p>
        )}
        {error && (
          <p className="error-panel" role="alert">
            {error}
          </p>
        )}
        <div className="quality-actions">
          <button
            className="secondary"
            disabled={busy || stale}
            onClick={() => void save("draft")}
          >
            {busy ? "Saving…" : "Save draft"}
          </button>
          <button
            className="primary"
            disabled={busy || stale || !showOutput}
            onClick={() => void save("completed", !!onNext)}
          >
            {onNext ? "Complete & next case" : "Complete case"}
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={() =>
              download(`draft-${caseData.id}.json`, {
                sessionId: session.id,
                caseId: caseData.id,
                annotation: draft,
              })
            }
          >
            Download this draft
          </button>
          {(stale || error) && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    "Discard this browser draft and load the saved version? Download the draft first if you want to keep it.",
                  )
                ) {
                  try {
                    sessionStorage.removeItem(storageKey);
                  } catch {
                    /* reload server state */
                  }
                  window.location.reload();
                }
              }}
            >
              Load saved version
            </button>
          )}
        </div>
        <p className="muted small">
          Choose an answer for each question and a reason for each verdict. All
          written notes are optional. “Uncertain” is a valid completed
          assessment and is not an approved reference.
        </p>
      </section>
    </article>
  );
}
