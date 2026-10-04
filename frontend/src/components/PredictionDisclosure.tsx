import { useState } from "react";
export function PredictionDisclosure({
  caseIdentity,
  source,
  prediction,
}: {
  caseIdentity: string;
  source: string;
  prediction: string;
}) {
  return (
    <Disclosure
      key={`${caseIdentity}:${source}`}
      source={source}
      prediction={prediction}
    />
  );
}
function Disclosure({
  source,
  prediction,
}: {
  source: string;
  prediction: string;
}) {
  const [revealed, setRevealed] = useState(false);
  return (
    <section>
      <h3>Prediction</h3>
      {revealed ? (
        <>
          <p>{prediction}</p>
          <p className="muted">{source}</p>
        </>
      ) : (
        <p className="muted">Hidden until you reveal it.</p>
      )}
      <button type="button" onClick={() => setRevealed(!revealed)}>
        {revealed ? "Hide prediction" : "Reveal prediction"}
      </button>
    </section>
  );
}
