import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/instrument-sans";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@xyflow/react/dist/base.css";
import "./styles/tokens.css";
import "./styles/themes.css";
import "./styles/app.css";
import "./styles/tableau.css";
import { App } from "./App";

createRoot(document.getElementById("racine")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
