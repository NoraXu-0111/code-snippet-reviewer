import { useRef, useState } from "react";
import {
  request,
  useResource,
  type Finding,
  type ReviewDetail,
  type ReviewRun,
} from "./api";
import { FindingCard } from "./FindingCard";

export function ReviewPanel({
  snippetId,
  latestReview,
  onStarted,
  selectedFindingId,
  onSelectFinding,
}: {
  snippetId: string;
  latestReview: ReviewRun | null;
  onStarted: () => void;
  selectedFindingId?: string;
  onSelectFinding: (finding: Finding) => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const sending = useRef(false);
  const [submitError, setSubmitError] = useState("");
  const { data, error, retry, update } = useResource<ReviewDetail>(
    latestReview ? `/reviews/${latestReview.id}` : null,
    (data) =>
      data.review.status === "queued" || data.review.status === "running",
  );
  const review = data?.review ?? latestReview;
  const active = review?.status === "queued" || review?.status === "running";
  async function start() {
    if (sending.current || active) return;
    sending.current = true;
    setSubmitting(true);
    setSubmitError("");
    try {
      await request<ReviewRun>(`/snippets/${snippetId}/reviews`, {
        method: "POST",
      });
      onStarted();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Could not start the review.",
      );
    } finally {
      sending.current = false;
      setSubmitting(false);
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
      {error && (
        <div className="review-error" role="alert">
          Unable to refresh this review: {error}
          <button className="text-button" onClick={retry}>
            Retry connection
          </button>
        </div>
      )}
      <button
        className="primary review-button"
        disabled={submitting || active}
        onClick={start}
      >
        {submitting
          ? "Starting…"
          : active
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
