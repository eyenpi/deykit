// Authored components for browser tests only. This entry is not part of the production build.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { StagedDialog } from "../src/components/Modal";
import { JsonSourceEditor } from "../src/components/JsonSourceEditor";
import { PredictionDisclosure } from "../src/components/PredictionDisclosure";
import "../src/styles.css";
function Harness() {
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState("");
  const [saved, setSaved] = useState("");
  const [caseId, setCaseId] = useState("a");
  return (
    <main className="document">
      <h1>Authored component tests</h1>
      <button onClick={() => setOpen(true)}>Edit input</button>
      <p role="status">{saved ? "Saved" : "Not saved"}</p>
      <button onClick={() => setCaseId(caseId === "a" ? "b" : "a")}>
        Next case
      </button>
      <PredictionDisclosure
        caseIdentity={caseId}
        source="Authored run"
        prediction={`Authored prediction ${caseId}`}
      />
      {open && (
        <StagedDialog
          title="Input"
          dirty={source !== saved}
          onSave={async () => {
            setSaved(source);
          }}
          onDiscard={() => setSource(saved)}
          onClose={() => setOpen(false)}
        >
          <div className="modal-body">
            <JsonSourceEditor
              label="JSON source"
              value={source}
              onChange={setSource}
            />
          </div>
        </StagedDialog>
      )}
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<Harness />);
