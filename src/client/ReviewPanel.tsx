import { useEffect, useRef, useState } from "react";
import {
  request,
  useResource,
  type Finding,
  type ReviewDetail,
  type ReviewRun,
} from "./api";
import { FindingCard } from "./FindingCard";
import { ModelPicker, useModelChoice } from "./ModelPicker";

type Submission = { clientRequestId: string; model: string | null };
function readSubmission(key: string): Submission | null {
  const raw = sessionStorage.getItem(key);
  if (!raw) return null;
  // Preserve request IDs from versions before model selection.
  if (/^[0-9a-f-]{36}$/i.test(raw))
    return { clientRequestId: raw, model: null };
  const parsed = JSON.parse(raw);
  if (
    typeof parsed.clientRequestId !== "string" ||
    (parsed.model !== null && typeof parsed.model !== "string")
  )
    throw new Error(
      "The saved review submission is unreadable. Refresh status before starting another review.",
    );
  return parsed;
}

export function ReviewPanel({
  snippetId,
  latestReview,
  reviewRun,
  discussionFindingId,
  onDiscuss,
  onStarted,
  selectedFindingId,
  onSelectFinding,
}: {
  snippetId: string;
  latestReview: ReviewRun | null;
  reviewRun: ReviewRun | null;
  discussionFindingId?: string;
  onDiscuss: (finding: Finding) => void;
  onStarted: () => void;
  selectedFindingId?: string;
  onSelectFinding: (finding: Finding) => void;
}) {
  const choice = useModelChoice();
  const storageKey = `review-submission:${snippetId}`;
  const [pending, setPending] = useState(() => {
    try {
      return readSubmission(storageKey);
    } catch {
      return null;
    }
  });
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const [submitting, setSubmitting] = useState(false);
  const sending = useRef(false);
  const [submitError, setSubmitError] = useState("");
  const { data, error, retry, update } = useResource<ReviewDetail>(
    reviewRun ? `/reviews/${reviewRun.id}` : null,
    (data) =>
      data.review.status === "queued" || data.review.status === "running",
  );
  const review = data?.review ?? reviewRun;
  const latestActive =
    latestReview?.status === "queued" || latestReview?.status === "running";
  const active = review?.status === "queued" || review?.status === "running";
  async function start() {
    if (sending.current || (!pending && (latestActive || !choice.model)))
      return;
    sending.current = true;
    setSubmitting(true);
    setSubmitError("");
    try {
      // Persist before sending: a lost response/reload must reuse this identity.
      let submission: Submission;
      try {
        submission = readSubmission(storageKey) ?? {
          clientRequestId: crypto.randomUUID(),
          model: choice.model!,
        };
        sessionStorage.setItem(storageKey, JSON.stringify(submission));
      } catch {
        throw new Error(
          "Browser storage is unavailable. Enable it before starting a review so interrupted submissions can be recovered.",
        );
      }
      setPending(submission);
      await request<ReviewRun>(`/snippets/${snippetId}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(submission),
      });
      if (!mounted.current) return;
      // Storage failure keeps recovery available; replaying is safe.
      if (sessionStorage.getItem(storageKey) === JSON.stringify(submission))
        sessionStorage.removeItem(storageKey);
      setPending(null);
      onStarted();
    } catch (error) {
      if (!mounted.current) return;
      setSubmitError(
        error instanceof Error ? error.message : "Could not start the review.",
      );
    } finally {
      sending.current = false;
      if (mounted.current) setSubmitting(false);
    }
  }
  return (
    <aside className="panel review-panel" aria-label="AI review">
      <div className="review-heading">
        <div>
          <p className="eyebrow">AI CODE REVIEW</p>
          <h2>
            {active
              ? "Review in progress"
              : review?.status === "failed"
                ? "Review failed"
                : review?.status === "succeeded"
                  ? "Review findings"
                  : "Ready for a fresh look"}
          </h2>
        </div>
      </div>
      {!review && (
        <p className="muted">
          Find potential bugs, security risks, and useful improvements in this
          snippet.
        </p>
      )}
      {active && (
        <p className="review-progress" role="status">
          <span className="spinner" aria-hidden="true" />
          {review.status === "queued"
            ? "Waiting to start…"
            : "Analyzing your code…"}{" "}
          You can leave this page and come back.
        </p>
      )}
      {review?.status === "failed" && (
        <p className="review-error" role="alert">
          {review.error}
        </p>
      )}
      {submitError && (
        <p className="review-error" role="alert">
          {submitError}{" "}
          <button className="text-button" onClick={onStarted}>
            Refresh status
          </button>
        </p>
      )}
      {pending && (
        <p className="review-disclosure" role="status">
          A submission is awaiting confirmation. Check submission safely
          recovers the same review, even if it has already finished.
        </p>
      )}
      {error && (
        <div className="review-error" role="alert">
          Unable to refresh this review: {error}
          <button className="text-button" onClick={retry}>
            Retry connection
          </button>
        </div>
      )}
      {review && (
        <p className="muted small">
          Review model: {review.model ?? "Not recorded (older review)"}
        </p>
      )}
      <ModelPicker
        choice={choice}
        label="Model for next review"
        disabled={submitting || latestActive || !!pending}
        frozenModel={pending?.model}
      />
      <button
        className="primary review-button"
        disabled={submitting || (!pending && (latestActive || !choice.model))}
        onClick={start}
      >
        {submitting
          ? "Starting…"
          : pending
            ? "Check submission"
            : latestActive
              ? "Reviewing…"
              : review?.status === "failed"
                ? "Retry review"
                : review
                  ? "Run new review"
                  : "Review snippet"}
      </button>
      {!active && (
        <p className="review-disclosure">
          Sends this snippet’s code to OpenAI for analysis.
        </p>
      )}
      {review?.status === "succeeded" && !data && !error && (
        <p role="status" className="muted">
          Loading findings…
        </p>
      )}
      {data?.review.status === "succeeded" && (
        <div className="findings">
          {data.findings.length > 0 && (
            <p className="resolution-help">
              Accept acknowledges an issue; it does not change the code.
            </p>
          )}
          <p className="findings-count">
            {data.findings.length} finding
            {data.findings.length === 1 ? "" : "s"}
            {data.findings.length > 0 &&
              ` · ${data.findings.filter((finding) => finding.resolution === "open").length} open`}
          </p>
          {data.findings.length === 0 && (
            <div className="no-findings">
              <h3>No issues found</h3>
              <p>
                The review completed without actionable findings. This is not a
                guarantee that the code is bug-free.
              </p>
            </div>
          )}
          {data.findings.map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              selected={selectedFindingId === finding.id}
              onSelect={onSelectFinding}
              onDiscuss={onDiscuss}
              discussing={discussionFindingId === finding.id}
              onUpdated={(saved) =>
                update((current) => ({
                  ...current,
                  findings: current.findings.map((item) =>
                    item.id === saved.id ? saved : item,
                  ),
                }))
              }
            />
          ))}
        </div>
      )}
    </aside>
  );
}
