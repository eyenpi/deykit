import { useRef } from "react";

/** A render-owned token that distinguishes A→B→A transitions for the same IDs. */
export function useRenderedScopeEpoch(scope: string): number {
  const current = useRef({ scope, epoch: 0 });
  if (current.current.scope !== scope) {
    current.current = { scope, epoch: current.current.epoch + 1 };
  }
  return current.current.epoch;
}
