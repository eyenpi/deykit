import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
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
  focus = false,
}: {
  message: string;
  retry?: () => void;
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
    </div>
  );
}
