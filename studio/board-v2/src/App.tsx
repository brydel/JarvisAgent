import { useEffect, useMemo, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { MotionConfig } from "motion/react";
import { Board } from "./Board";
import { SourceDemo, SourceReelle, sessionValide } from "./api";

export function App() {
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const demo = params.get("demo") === "1";
  const charge = demo ? Math.min(1000, Number(params.get("charge") || 0)) : 0;
  const [session, setSession] = useState<"attente" | "ok" | "refus">(demo ? "ok" : "attente");
  const source = useMemo(() => (demo ? new SourceDemo() : new SourceReelle()), [demo]);
  useEffect(() => {
    if (!demo) sessionValide().then((ok) => setSession(ok ? "ok" : "refus"));
  }, [demo]);

  if (session === "attente") return <div className="porte" aria-busy="true" />;
  if (session === "refus") {
    return (
      <main className="porte-v2">
        <h1>Session requise</h1>
        <p>Ouvre le lien affiché par <code>jarvis mission studio</code> en remplaçant <code>/connexion</code> par <code>/v2/connexion</code>.</p>
        <p>Ou découvre le Board avec des données fictives : <a href="/v2/?demo=1">mode démo</a>.</p>
      </main>
    );
  }
  return (
    <MotionConfig reducedMotion="user">
      <ReactFlowProvider>
        <Board source={source} charge={charge || undefined} />
      </ReactFlowProvider>
    </MotionConfig>
  );
}
