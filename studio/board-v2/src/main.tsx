import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@xyflow/react/dist/base.css";
import "./styles/tokens.css";
import "./styles/app.css";
import { App } from "./App";

createRoot(document.getElementById("racine")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
