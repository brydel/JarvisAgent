import { Component, lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { MotionConfig } from "motion/react";
import { SourceDemo, SourceReelle, sessionValide } from "./api";
import { StudioNavigation, useStudioNavigation } from "./product/routing";
import { ProductStudio } from "./product/ProductStudio";
import type { Source } from "./api";

// Le graphe et les cartes ne sont chargés que lors de l'ouverture du Board.
const Workspace = lazy(() => import("./product/BoardWorkspace"));
class StudioBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <main className="porte-v2" role="alert"><h1>L'espace n'a pas pu s'afficher.</h1><p>Tes données enregistrées restent sur le serveur.</p><button onClick={() => location.reload()}>Recharger</button></main> : this.props.children; }
}
function Pages({ source, charge }: { source: Source; charge?: number }) {
  const { vue } = useStudioNavigation();
  return vue === "board" ? <Suspense fallback={<div className="p-loading" role="status">Ouverture du Board...</div>}><Workspace source={source} charge={charge}/></Suspense> : <ProductStudio source={source}/>;
}
export function App() {
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const demo = params.get("demo") === "1";
  const n = Number(params.get("charge") || 0);
  const charge = demo && Number.isFinite(n) ? Math.max(0, Math.min(1000, n)) : 0;
  const [session, setSession] = useState<"attente" | "ok" | "refus">(demo ? "ok" : "attente");
  const verificationSession = useRef<Promise<boolean> | null>(null);
  const source = useMemo(() => demo ? new SourceDemo() : new SourceReelle(), [demo]);
  useEffect(() => {
    let active = true;
    if (!demo) {
      // Une seule authentification, même lors du double effet de StrictMode en développement.
      // Le premier appel retire le fragment secret ; un second GET prématuré pourrait refuser la session.
      verificationSession.current ??= sessionValide();
      verificationSession.current.then(ok => { if (active) setSession(ok ? "ok" : "refus"); });
    }
    return () => { active = false; };
  }, [demo]);
  if (session === "attente") return <div className="p-loading" role="status">Connexion à ton espace...</div>;
  if (session === "refus") return <main className="porte-v2"><h1>Ton équipe t'attend.</h1><p>Ouvre le lien V2 fourni par <code>jarvis mission studio</code>.</p><a className="p-button p-primary" href="/v2/?demo=1&vue=accueil">Découvrir Jarvis sans connexion</a><p>Démonstration uniquement. Aucun agent réel n'est lancé.</p></main>;
  return <StudioBoundary><MotionConfig reducedMotion="user"><StudioNavigation><Pages source={source} charge={charge || undefined}/></StudioNavigation></MotionConfig></StudioBoundary>;
}
