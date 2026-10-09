import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { createWorkspaceGateway } from "./workspace/workspace-adapter";
import "./styles.css";
const gateway = createWorkspaceGateway();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App gateway={gateway} />
  </StrictMode>,
);
