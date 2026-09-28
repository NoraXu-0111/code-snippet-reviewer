import { useMemo } from "react";
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
}: {
  code: string;
  language: string;
}) {
  const display = code.replace(/\r\n|\r/g, "\n");
  const highlighted = useMemo(() => {
    if (!hljs.getLanguage(language)) return null;
    try {
      return hljs.highlight(display, { language, ignoreIllegals: true }).value;
    } catch {
      return null;
    }
  }, [display, language]);
  return (
    <div
      className="code-scroll"
      role="region"
      aria-label="Snippet source code"
      tabIndex={0}
    >
      <div className="code-grid">
        <pre className="line-numbers" aria-hidden="true">
          {display
            .split("\n")
            .map((_, i) => i + 1)
            .join("\n")}
        </pre>
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
  );
}
