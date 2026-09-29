import { useEffect, useId, useState } from "react";
import { useResource } from "./api";
import type { components } from "../shared/api-types";

type Catalog = components["schemas"]["ModelCatalog"];
const preferenceKey = "preferred-openai-model";
const preferenceEvent = "model-preference-changed";
function readPreference() {
  try {
    return localStorage.getItem(preferenceKey);
  } catch {
    return null;
  }
}

export function useModelChoice() {
  const resource = useResource<Catalog>("/models");
  const [preferred, setPreferred] = useState(readPreference);
  const [storageError, setStorageError] = useState(false);
  useEffect(() => {
    const refresh = () => setPreferred(readPreference());
    window.addEventListener("storage", refresh);
    window.addEventListener(preferenceEvent, refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener(preferenceEvent, refresh);
    };
  }, []);
  const model = resource.data?.models.some((item) => item.id === preferred)
    ? preferred!
    : resource.data?.defaultModel;
  function select(model: string) {
    setPreferred(model);
    try {
      localStorage.setItem(preferenceKey, model);
      setStorageError(false);
      window.dispatchEvent(new Event(preferenceEvent));
    } catch {
      setStorageError(true);
    }
  }
  return { ...resource, model, select, storageError };
}

export function ModelPicker({
  choice,
  label,
  disabled,
  frozenModel,
}: {
  choice: ReturnType<typeof useModelChoice>;
  label: string;
  disabled: boolean;
  frozenModel?: string | null;
}) {
  const id = useId();
  const selected = frozenModel ?? choice.model ?? "";
  const options = choice.data?.models ?? [];
  return (
    <div className="model-picker">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={selected}
        disabled={disabled || !choice.data}
        onChange={(event) => choice.select(event.target.value)}
      >
        {!choice.data && (
          <option value={selected}>{selected || "Loading models…"}</option>
        )}
        {choice.data &&
          selected &&
          !options.some((item) => item.id === selected) && (
            <option value={selected}>{selected} (original request)</option>
          )}
        {options.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
            {item.id === choice.data?.defaultModel ? " (app default)" : ""}
          </option>
        ))}
      </select>
      <p className="muted small">
        OpenAI only. Your choice is remembered for new requests in this browser.
      </p>
      {choice.storageError && (
        <p className="muted small">
          Your choice applies here, but browser storage could not remember it.
        </p>
      )}
      {choice.error && (
        <p className="review-error" role="alert">
          Could not load models.{" "}
          <button type="button" className="text-button" onClick={choice.retry}>
            Retry models
          </button>
        </p>
      )}
    </div>
  );
}
