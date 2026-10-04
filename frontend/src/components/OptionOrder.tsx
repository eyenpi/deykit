import { useState } from "react";
export interface OptionPresentation {
  id: string;
  name: string;
  description?: string;
}
/** Presentation order only. Validation and stable ID allocation belong to the service. */
export function OptionOrder({
  options,
  onChange,
}: {
  options: readonly OptionPresentation[];
  onChange: (options: readonly OptionPresentation[]) => void;
}) {
  const [announcement, setAnnouncement] = useState("");
  function move(index: number, offset: number) {
    const next = [...options];
    const target = index + offset;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
    setAnnouncement(`${options[index].name} moved to position ${target + 1}.`);
  }
  return (
    <>
      <ol className="option-list">
        {options.map((option, index) => (
          <li key={option.id}>
            <div>
              <strong>{option.name}</strong>
              {option.description && (
                <p className="muted">{option.description}</p>
              )}
            </div>
            <div className="actions">
              <button
                type="button"
                aria-label={`Move ${option.name} up`}
                disabled={index === 0}
                onClick={() => move(index, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                aria-label={`Move ${option.name} down`}
                disabled={index === options.length - 1}
                onClick={() => move(index, 1)}
              >
                ↓
              </button>
            </div>
          </li>
        ))}
      </ol>
      <p className="visually-hidden" role="status">
        {announcement}
      </p>
    </>
  );
}
