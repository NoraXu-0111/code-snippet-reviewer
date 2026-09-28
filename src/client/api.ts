import { useEffect, useState } from "react";
import type { components } from "../shared/api-types";
export type Snippet = components["schemas"]["Snippet"];
export type SnippetDetail = components["schemas"]["SnippetDetail"];
export type SnippetList = components["schemas"]["SnippetList"];
export type ReviewStatus =
  components["schemas"]["SnippetSummary"]["reviewStatus"];
export async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new Error(
      body?.error?.message ?? `Request failed (${response.status})`,
    );
  return body as T;
}
export function useResource<T>(path: string) {
  const [result, setResult] = useState<{
    path: string;
    data?: T;
    error?: string;
  }>({ path });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setResult({ path });
    request<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ path, data });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setResult({
            path,
            error: error instanceof Error ? error.message : "Connection failed",
          });
      });
    return () => controller.abort();
  }, [path, attempt]);
  return {
    ...(result.path === path ? result : {}),
    retry: () => setAttempt((value) => value + 1),
  };
}
export const statusLabels: Record<ReviewStatus, string> = {
  not_reviewed: "Not reviewed",
  in_progress: "In progress",
  reviewed: "Reviewed",
  failed: "Failed",
};
export const languages = [
  ["python", "Python"],
  ["typescript", "TypeScript"],
  ["javascript", "JavaScript"],
  ["go", "Go"],
  ["rust", "Rust"],
  ["java", "Java"],
  ["cpp", "C++"],
  ["sql", "SQL"],
  ["plaintext", "Other / plain text"],
] as const;
export const languageLabel = (language: string) =>
  languages.find(([id]) => id === language)?.[1] ?? language;
export const formatDate = (value: string) =>
  new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
