import { useEffect, useRef, useState } from "react";
import type { components } from "../shared/api-types";
export type Snippet = components["schemas"]["Snippet"];
export type SnippetDetail = components["schemas"]["SnippetDetail"];
export type SnippetList = components["schemas"]["SnippetList"];
export type ReviewStatus =
  components["schemas"]["SnippetSummary"]["reviewStatus"];
export type DiscussionTurn = components["schemas"]["DiscussionTurn"];
export type DiscussionDetail = components["schemas"]["DiscussionDetail"];
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      body?.error?.message ?? `Request failed (${response.status})`,
      response.status,
    );
  if (body === null)
    throw new Error(
      "The server returned an unreadable response. Please refresh.",
    );
  return body as T;
}
export type ReviewRun = components["schemas"]["ReviewRun"];
export type ReviewHistory = components["schemas"]["ReviewHistory"];
export type ReviewDetail = components["schemas"]["ReviewDetail"];
export type Finding = components["schemas"]["Finding"];
export function useResource<T>(
  path: string | null,
  pollWhile?: (data: T) => boolean,
) {
  const [result, setResult] = useState<{
    path: string | null;
    data?: T;
    error?: string;
  }>({ path });
  const [attempt, setAttempt] = useState(0);
  const polling = useRef(pollWhile);
  polling.current = pollWhile;
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setResult({ path });
    if (!path) return () => controller.abort();
    async function refresh() {
      try {
        const data = await request<T>(path!, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setResult({ path, data });
        if (polling.current?.(data)) timer = setTimeout(refresh, 2000);
      } catch (error) {
        if (controller.signal.aborted) return;
        setResult((previous) => ({
          ...previous,
          path,
          error: error instanceof Error ? error.message : "Connection failed",
        }));
        if (polling.current) timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [path, attempt]);
  return {
    ...(result.path === path ? result : {}),
    retry: () => setAttempt((value) => value + 1),
    update: (transform: (data: T) => T) =>
      setResult((previous) =>
        previous.path === path && previous.data
          ? { ...previous, data: transform(previous.data) }
          : previous,
      ),
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
