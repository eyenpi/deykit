import type { OptionPresentation } from "./OptionOrder";
export function ExpectedAnswers({
  options,
  selected,
  onChange,
  onSave,
  saving = false,
  disabled = false,
}: {
  options: readonly OptionPresentation[];
  selected: readonly string[];
  onChange: (ids: readonly string[]) => void;
  onSave: () => void;
  saving?: boolean;
  disabled?: boolean;
}) {
  return (
    <fieldset disabled={saving || disabled}>
      <legend>Expected answers</legend>
      <p className="muted">
        Select all acceptable options. Changes are saved only when you choose
        Save expected answer.
      </p>
      {options.map((option) => (
        <label className="check-row" key={option.id}>
          <input
            type="checkbox"
            checked={selected.includes(option.id)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...selected, option.id]
                  : selected.filter((id) => id !== option.id),
              )
            }
          />
          {option.name}
        </label>
      ))}
      <button
        type="button"
        className="primary"
        onClick={onSave}
        disabled={!selected.length || saving || disabled}
      >
        {saving ? "Saving…" : "Save expected answer"}
      </button>
      {!selected.length && (
        <p className="muted">
          Select an expected answer, or use the separate Clear label action.
        </p>
      )}
    </fieldset>
  );
}
