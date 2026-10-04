import { useId } from "react";
/** Controlled source only: incomplete, duplicate-key and high precision JSON stays intact. */
export function JsonSourceEditor({
  label,
  value,
  onChange,
  error,
  readOnly = false,
}: {
  label: string;
  value: string;
  onChange?: (source: string) => void;
  error?: string;
  readOnly?: boolean;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea
        id={id}
        className="source-editor"
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        readOnly={readOnly}
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        aria-invalid={!!error}
        aria-describedby={`${id}-help`}
      />
      <p id={`${id}-help`} className={error ? "field-error" : "muted"}>
        {error ??
          "Values and formatting are preserved. Validation is performed by the local service."}
      </p>
    </div>
  );
}
