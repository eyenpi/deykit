import { useId } from "react";
import type { CompositionEvent, FocusEvent } from "react";
/** Controlled source only: incomplete, duplicate-key and high precision JSON stays intact. */
export function JsonSourceEditor({
  label,
  value,
  onChange,
  error,
  description,
  rows = 10,
  readOnly = false,
  onCompositionStart,
  onCompositionEnd,
  onFocus,
  onBlur,
}: {
  label: string;
  value: string;
  onChange?: (source: string) => void;
  error?: string;
  description?: string;
  rows?: number;
  readOnly?: boolean;
  onCompositionStart?: (event: CompositionEvent<HTMLTextAreaElement>) => void;
  onCompositionEnd?: (event: CompositionEvent<HTMLTextAreaElement>) => void;
  onFocus?: (event: FocusEvent<HTMLTextAreaElement>) => void;
  onBlur?: (event: FocusEvent<HTMLTextAreaElement>) => void;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea
        id={id}
        className="source-editor"
        value={value}
        rows={rows}
        onCompositionStart={onCompositionStart}
        onCompositionEnd={onCompositionEnd}
        onFocus={onFocus}
        onBlur={onBlur}
        onChange={(event) => onChange?.(event.target.value)}
        readOnly={readOnly}
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        aria-invalid={!!error}
        aria-describedby={`${id}-help`}
      />
      <p id={`${id}-help`} className={error ? "field-error" : "muted"}>
        {error ?? description ??
          "Values and formatting are preserved. Validation is performed by the local service."}
      </p>
    </div>
  );
}
