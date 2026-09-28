import { useRef, useState } from "react";
import { request, type Finding } from "./api";
import { Discussion } from "./Discussion";

export function FindingCard({
  finding,
  selected,
  onSelect,
  onUpdated,
}: {
  finding: Finding;
  selected: boolean;
  onSelect: (finding: Finding) => void;
  onUpdated: (finding: Finding) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [discussing, setDiscussing] = useState(false);
  const [discussionLoaded, setDiscussionLoaded] = useState(false);
  const inFlight = useRef(false);
  async function resolve(resolution: Finding["resolution"]) {
    if (inFlight.current) return;
    inFlight.current = true;
    setSaving(true);
    setError("");
    try {
      const saved = await request<Finding>(`/findings/${finding.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution }),
      });
      // Display the confirmed server result. Failed writes leave the old state.
      onUpdated(saved);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not save this change. Please try again.",
      );
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }
  const range =
    finding.startLine === finding.endLine
      ? `line ${finding.startLine}`
      : `lines ${finding.startLine}–${finding.endLine}`;
  return (
    <article
      className={`finding ${selected ? "finding-selected" : ""}`}
      aria-label={`Finding at ${range}`}
    >
      <div className="finding-meta">
        <span className={`severity severity-${finding.severity}`}>
          {finding.severity}
        </span>
        <span>{finding.category}</span>
        <button
          className="finding-lines"
          onClick={() => onSelect(finding)}
          aria-label={`Show ${range} in code`}
          aria-pressed={selected}
        >
          L{finding.startLine}
          {finding.endLine !== finding.startLine ? `–${finding.endLine}` : ""}
        </button>
      </div>
      <p className="finding-description">{finding.description}</p>
      {finding.suggestedFix && (
        <details>
          <summary>Suggested fix</summary>
          <pre className="suggested-fix">{finding.suggestedFix}</pre>
        </details>
      )}
      <div className="finding-resolution" aria-live="polite">
        <span className={`resolution-label resolution-${finding.resolution}`}>
          {finding.resolution === "accepted"
            ? "Accepted"
            : finding.resolution === "dismissed"
              ? "Dismissed"
              : "Open"}
        </span>
        {saving && (
          <span className="saving-label" role="status">
            Saving…
          </span>
        )}
      </div>
      <div className="finding-actions">
        {finding.resolution !== "accepted" && (
          <button
            className="secondary"
            disabled={saving}
            onClick={() => resolve("accepted")}
          >
            Accept
          </button>
        )}
        {finding.resolution !== "dismissed" && (
          <button
            className="secondary"
            disabled={saving}
            onClick={() => resolve("dismissed")}
          >
            Dismiss
          </button>
        )}
        {finding.resolution !== "open" && (
          <button
            className="text-button"
            disabled={saving}
            onClick={() => resolve("open")}
          >
            Reopen
          </button>
        )}
      </div>
      <button
        className="text-button discuss-toggle"
        aria-expanded={discussing}
        aria-controls={`discussion-${finding.id}`}
        onClick={() => {
          setDiscussionLoaded(true);
          setDiscussing((value) => !value);
        }}
      >
        {discussing ? "Hide discussion" : "Discuss with AI"}
      </button>
      <div id={`discussion-${finding.id}`} hidden={!discussing}>
        {discussionLoaded && <Discussion findingId={finding.id} />}
      </div>
      {error && (
        <p className="review-error" role="alert">
          {error}
        </p>
      )}
    </article>
  );
}
