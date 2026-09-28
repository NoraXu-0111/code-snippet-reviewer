import { useRef, useState } from "react";
import { request, useResource, type ReviewDetail, type ReviewRun } from "./api";

export function ReviewPanel({
  snippetId,
  latestReview,
  onStarted,
}: {
  snippetId: string;
  latestReview: ReviewRun | null;
  onStarted: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const sending = useRef(false);
  const [submitError, setSubmitError] = useState("");
  const { data, error, retry } = useResource<ReviewDetail>(
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
          <p className="findings-count">
            {data.findings.length} finding
            {data.findings.length === 1 ? "" : "s"}
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
            <article className="finding" key={finding.id}>
              <div className="finding-meta">
                <span className={`severity severity-${finding.severity}`}>
                  {finding.severity}
                </span>
                <span>{finding.category}</span>
                <span className="finding-lines">
                  L{finding.startLine}
                  {finding.endLine !== finding.startLine
                    ? `–${finding.endLine}`
                    : ""}
                </span>
              </div>
              <p className="finding-description">{finding.description}</p>
              {finding.suggestedFix && (
                <details>
                  <summary>Suggested fix</summary>
                  <pre className="suggested-fix">{finding.suggestedFix}</pre>
                </details>
              )}
            </article>
          ))}
        </div>
      )}
    </aside>
  );
}
