import { useEffect, useMemo, useRef } from "react";
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import typescript from "highlight.js/lib/languages/typescript";
import javascript from "highlight.js/lib/languages/javascript";
import go from "highlight.js/lib/languages/go";
import rust from "highlight.js/lib/languages/rust";
import java from "highlight.js/lib/languages/java";
import cpp from "highlight.js/lib/languages/cpp";
import sql from "highlight.js/lib/languages/sql";
import "highlight.js/styles/github.css";
for (const [name, grammar] of Object.entries({
  python,
  typescript,
  javascript,
  go,
  rust,
  java,
  cpp,
  sql,
})) {
  hljs.registerLanguage(name, grammar);
}
export function CodeView({
  code,
  language,
  selection,
}: {
  code: string;
  language: string;
  selection?: { startLine: number; endLine: number } | null;
}) {
  const scrollRegion = useRef<HTMLDivElement>(null);
  const display = code.replace(/\r\n|\r/g, "\n");
  const highlighted = useMemo(() => {
    if (!hljs.getLanguage(language)) return null;
    try {
      return hljs.highlight(display, { language, ignoreIllegals: true }).value;
    } catch {
      return null;
    }
  }, [display, language]);
  useEffect(() => {
    if (!selection || !scrollRegion.current) return;
    const region = scrollRegion.current;
    const line = region.querySelector<HTMLElement>(
      `[data-line="${selection.startLine}"]`,
    );
    region.scrollLeft = 0;
    line?.scrollIntoView({
      block: "center",
      inline: "nearest",
      behavior: "instant",
    });
    region.focus({ preventScroll: true });
  }, [selection]);
  return (
    <div
      className="code-scroll"
      ref={scrollRegion}
      role="region"
      aria-label="Snippet source code"
      tabIndex={0}
    >
      <div className="code-grid">
        <div className="line-numbers" aria-hidden="true">
          {display.split("\n").map((_, index) => {
            const line = index + 1;
            const selected =
              selection &&
              line >= selection.startLine &&
              line <= selection.endLine;
            return (
              <span
                key={line}
                data-line={line}
                className={`line-number ${selected ? "line-number-selected" : ""}`}
              >
                {line}
              </span>
            );
          })}
        </div>
        <div className="source-wrap">
          {selection && (
            <div
              className="line-selection"
              aria-hidden="true"
              style={{
                top: `${(selection.startLine - 1) * 1.9}em`,
                height: `${(selection.endLine - selection.startLine + 1) * 1.9}em`,
              }}
            />
          )}
          <pre className="source-code">
            {highlighted === null ? (
              <code>{display}</code>
            ) : (
              // Only highlight.js output is inserted; it escapes the submitted source.
              <code
                className="hljs"
                dangerouslySetInnerHTML={{ __html: highlighted }}
              />
            )}
          </pre>
        </div>
      </div>
    </div>
  );
}
