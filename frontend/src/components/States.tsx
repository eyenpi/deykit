import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import type { ApiWarning } from "../api/client";
export function LoadingState({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="muted">
      {children}
    </p>
  );
}
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="empty-state">
      <h2>{title}</h2>
      <p className="muted">{children}</p>
      {action}
    </section>
  );
}
export function ErrorSummary({
  message,
  retry,
  reconnect,
  focus = false,
}: {
  message: string;
  retry?: () => void;
  reconnect?: () => void;
  focus?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focus) ref.current?.focus();
  }, [focus, message]);
  return (
    <div ref={ref} className="error-summary" role="alert" tabIndex={-1}>
      <p>{message}</p>
      {retry && <button onClick={retry}>Try again</button>}
      {reconnect && <button onClick={reconnect}>Reconnect</button>}
    </div>
  );
}

export function WarningList({ warnings }: { warnings: readonly ApiWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <section className="warning-summary" role="status" aria-label="Warnings">
      <ul>
        {warnings.map((warning, index) => (
          <li key={`${warning.code}-${index}`}>
            <strong>{warning.code}</strong>: {warning.message}
            <span className="warning-details">
              {warning.reason && <> Reason: <code>{warning.reason}</code>.</>}
              {warning.resource_id && <> Resource: <code>{warning.resource_id}</code>.</>}
              {warning.row !== undefined && warning.row !== null && (
                <> Row: <code>{warning.row}</code>.</>
              )}
              {warning.correlation_id && <> Reference: <code>{warning.correlation_id}</code>.</>}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
