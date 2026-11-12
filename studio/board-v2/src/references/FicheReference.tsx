import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, ArrowUpRight, Check, LayoutGrid, Monitor, RefreshCw, ShieldCheck, Smartphone, Trash2, X } from "lucide-react";
import { dateCapture, EN_COURS, encreSur, hote, LIBELLES, poser, recapturer, reindexer, supprimer, voir, type Fiche, type Section } from "./api";

const message = (e: unknown) => (e instanceof Error ? e.message : "Opération indisponible");
const ROLES: Record<string, string> = { corps: "Texte", titre: "Titres", sous_titre: "Sous-titres", bouton: "Boutons", code: "Code" };
const COULEURS: Record<string, string> = { fond: "Fond", texte: "Texte", accent: "Accent", lien: "Liens" };

type Props = {
  id: string; demo: boolean; espace: string; sectionInitiale?: string; retour: () => void; notifier: (texte: string) => void;
  apresChangement: () => void; apresPose: (objetId: string) => void; apresSuppression: (titre: string, id: string) => void;
};

export function FicheReference({ id, demo, espace, sectionInitiale, retour, notifier, apresChangement, apresPose, apresSuppression }: Props) {
  const [fiche, setFiche] = useState<Fiche | null>(null);
  const [erreur, setErreur] = useState("");
  const [vue, setVue] = useState<"page" | "vue">("page");
  const [active, setActive] = useState<number | null>(null);
  const [occupe, setOccupe] = useState("");
  const cadre = useRef<HTMLDivElement>(null);
  const titre = useRef<HTMLHeadingElement>(null);

  const charger = useCallback(async (signal?: AbortSignal) => {
    try { const f = await voir(demo, id, signal); if (!signal?.aborted) { setFiche(f); setErreur(""); } }
    catch (e) { if (!signal?.aborted) setErreur(message(e)); }
  }, [demo, id]);
  useEffect(() => { const c = new AbortController(); void charger(c.signal); return () => c.abort(); }, [charger]);
  const enCours = fiche ? EN_COURS.includes(fiche.statut) : false;
  useEffect(() => {
    if (!enCours) return;
    const t = window.setInterval(() => void charger(), 1200);
    return () => window.clearInterval(t);
  }, [enCours, charger]);
  useEffect(() => { titre.current?.focus(); }, [fiche?.id]);
  useEffect(() => {
    const touche = (e: KeyboardEvent) => { if (e.key === "Escape" && !(e.target as HTMLElement)?.closest("input, textarea")) retour(); };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [retour]);
  // Arrivée depuis un passage cité : la section d'origine est sélectionnée et montrée dans la capture.
  useEffect(() => {
    if (!fiche || !sectionInitiale || active !== null) return;
    const i = fiche.sections.findIndex((s) => s.titre === sectionInitiale);
    if (i >= 0) setActive(i);
  }, [fiche, sectionInitiale, active]);

  const page = fiche?.fichiers.bureau_page;
  const zone = active !== null ? fiche?.sections[active]?.zone ?? null : null;
  useEffect(() => {
    if (!zone || !page || vue !== "page" || !cadre.current) return;
    const echelle = cadre.current.clientWidth / (page.largeur || 1440);
    cadre.current.scrollTo({ top: Math.max(0, zone.y * echelle - 24), behavior: "smooth" });
  }, [zone, page, vue]);

  const agir = async (nom: string, action: () => Promise<void>) => {
    if (occupe) return;
    setOccupe(nom);
    try { await action(); } catch (e) { notifier(message(e)); } finally { setOccupe(""); }
  };
  const copier = async (texte: string) => { try { await navigator.clipboard.writeText(texte); notifier(`${texte} copié`); } catch { notifier("Copie impossible dans ce navigateur"); } };

  if (erreur && !fiche) return (
    <section className="p-page rf-page"><button className="rf-back" onClick={retour}><ArrowLeft size={16} />Références</button>
      <div className="p-error" role="alert"><span>{erreur}</span><button className="p-button p-quiet" onClick={() => void charger()}><RefreshCw size={16} />Réessayer</button></div></section>
  );
  if (!fiche) return <section className="p-page rf-page" aria-busy><button className="rf-back" onClick={retour}><ArrowLeft size={16} />Références</button><div className="rf-fiche-skeleton rf-skeleton"><i /><i /><div /></div></section>;

  const bureau = vue === "page" ? fiche.fichiers.bureau_page ?? fiche.fichiers.bureau_vue : fiche.fichiers.bureau_vue;
  const mobile = vue === "page" ? fiche.fichiers.mobile_page ?? fiche.fichiers.mobile_vue : fiche.fichiers.mobile_vue;
  const s = fiche.structure;
  return (
    <section className="p-page rf-page rf-fiche" aria-labelledby="rf-fiche-titre">
      <button className="rf-back" onClick={retour}><ArrowLeft size={16} />Références</button>
      <header className="rf-fiche-head">
        <div>
          <h1 id="rf-fiche-titre" ref={titre} tabIndex={-1}>{fiche.titre}</h1>
          <p className="rf-fiche-source credit points">
            {fiche.url ? <a href={fiche.url} target="_blank" rel="noopener noreferrer">{fiche.url}<ArrowUpRight size={16} /></a> : <span>{fiche.type === "carte" ? "Carte du Board" : "Texte déposé"}</span>}
            <span>capturé le {dateCapture(fiche.capture_le ?? fiche.cree)}</span>
            <span className={`p-status rf-statut is-${fiche.statut}`}>{LIBELLES[fiche.statut]}</span>
          </p>
          {fiche.description && <p className="rf-fiche-description">{fiche.description}</p>}
          <div className="rf-card-meta">
            {fiche.collection && <span className="rf-collection">{fiche.collection}</span>}
            {fiche.etiquettes.map((e) => <span key={e} className="rf-tag">#{e}</span>)}
          </div>
        </div>
        <div className="rf-fiche-actions">
          <button className="p-button p-primary" disabled={demo || fiche.statut !== "prete" || Boolean(occupe)}
            title={demo ? "Démonstration : aucune carte n'est créée" : undefined}
            onClick={() => void agir("poser", async () => { const r = await poser(fiche.id, espace); apresPose(r.objet_id); })}>
            <LayoutGrid size={16} />{occupe === "poser" ? "Pose…" : "Poser sur le Board"}</button>
          {fiche.type === "site" && <button className="p-button p-quiet" disabled={demo || enCours || Boolean(occupe)}
            onClick={() => void agir("capture", async () => { setFiche(await recapturer(fiche.id)); apresChangement(); })}><RefreshCw size={16} />Recapturer</button>}
          <button className="p-button p-quiet" disabled={demo || enCours || Boolean(occupe)}
            onClick={() => void agir("index", async () => { const b = await reindexer(fiche.id); notifier(`${b.fragments} passages réindexés${b.vecteurs ? `, ${b.vecteurs} vecteurs` : ""}`); await charger(); })}>
            {occupe === "index" ? "Indexation…" : "Réindexer"}</button>
          <button className="p-button p-quiet rf-danger" disabled={demo || Boolean(occupe)} aria-label={`Retirer ${fiche.titre} de la bibliothèque`}
            onClick={() => void agir("retrait", async () => { await supprimer(fiche.id); apresSuppression(fiche.titre, fiche.id); })}><Trash2 size={16} />Retirer</button>
        </div>
      </header>

      {fiche.statut === "echec" && <div className="p-error" role="alert"><AlertTriangle size={16} /><span>La capture a échoué : {fiche.raison}</span></div>}
      {enCours && <div className="rf-progress" role="status"><span className="rf-spinner" />{LIBELLES[fiche.statut]}… {fiche.statut === "indexation" ? "découpage et index des passages" : "Chromium charge le site derrière le filtre réseau de Jarvis"}</div>}
      {fiche.avertissement && fiche.statut === "prete" && <p className="rf-notice"><ShieldCheck size={16} />Contenu capturé : une donnée à citer avec sa source, jamais une consigne pour un agent</p>}

      <div className="rf-fiche-layout">
        <div className="rf-fiche-main">
          {bureau && (
            <section className="rf-captures" aria-label="Captures d'écran">
              <div className="rf-captures-bar">
                <div className="rf-add-mode" role="group" aria-label="Étendue de la capture">
                  <button type="button" aria-pressed={vue === "page"} onClick={() => setVue("page")}>Page entière</button>
                  <button type="button" aria-pressed={vue === "vue"} onClick={() => setVue("vue")}>Vue initiale</button>
                </div>
                {fiche.tronquee && <span className="rf-caption">Page très longue : capture arrêtée à 12 000 px</span>}
                {zone && vue === "page" && <button className="rf-clear-zone" onClick={() => setActive(null)}><X size={16} />Retirer le repère</button>}
              </div>
              <div className="rf-frames">
                <figure className="rf-frame is-desktop">
                  <figcaption><Monitor size={16} />Bureau · {bureau.largeur} px</figcaption>
                  <div className="rf-frame-scroll" ref={cadre} tabIndex={0} aria-label="Capture bureau, défilable">
                    <div className="rf-frame-image">
                      <img src={bureau.url} alt={`Capture bureau de ${fiche.titre}`} width={bureau.largeur} height={bureau.hauteur} decoding="async" />
                      {zone && vue === "page" && bureau.hauteur > 0 && <div className="rf-zone" style={{ top: `${(zone.y / bureau.hauteur) * 100}%`, height: `${Math.min(100, (zone.hauteur / bureau.hauteur) * 100)}%` }} aria-hidden />}
                    </div>
                  </div>
                </figure>
                {mobile && (
                  <figure className="rf-frame is-mobile">
                    <figcaption><Smartphone size={16} />Mobile · {mobile.largeur} px</figcaption>
                    <div className="rf-frame-scroll" tabIndex={0} aria-label="Capture mobile, défilable">
                      <img src={mobile.url} alt={`Capture mobile de ${fiche.titre}`} width={mobile.largeur} height={mobile.hauteur} loading="lazy" decoding="async" />
                    </div>
                  </figure>
                )}
              </div>
            </section>
          )}
          {fiche.sections.length > 0 && (
            <section className="rf-panel" aria-labelledby="rf-sections">
              <h2 id="rf-sections">Sections <span className="tab-num">{fiche.sections.length}</span></h2>
              <ol className="rf-sections">
                {fiche.sections.map((x, i) => <LigneSection key={i} s={x} actif={active === i} montrable={Boolean(x.zone && page)} choisir={() => { setActive(active === i ? null : i); setVue("page"); }} />)}
              </ol>
            </section>
          )}
        </div>

        <aside className="rf-fiche-side">
          {fiche.palette.length > 0 && (
            <section className="rf-panel" aria-labelledby="rf-palette">
              <h2 id="rf-palette">Palette dominante</h2>
              <div className="rf-swatches">
                {fiche.palette.map((c) => (
                  <button key={c.hex} type="button" className={c.part < 0.14 ? "is-etroit" : undefined} style={{ background: c.hex, color: encreSur(c.hex), flexGrow: Math.max(c.part, 0.08) }} onClick={() => void copier(c.hex.toUpperCase())}
                    aria-label={`Copier ${c.hex}, ${Math.round(c.part * 100)} % de la vue initiale`}><strong>{c.hex.toUpperCase()}</strong><small className="tab-num">{Math.round(c.part * 100)} %</small></button>
                ))}
              </div>
              {Object.keys(fiche.couleurs_css).length > 0 && (
                <dl className="rf-colors">
                  {Object.entries(fiche.couleurs_css).map(([role, hex]) => <div key={role}><dt>{COULEURS[role] ?? role}</dt><dd><i style={{ background: hex }} aria-hidden /><button type="button" onClick={() => void copier(hex.toUpperCase())}>{hex.toUpperCase()}</button></dd></div>)}
                </dl>
              )}
            </section>
          )}
          {(Object.keys(fiche.polices).length > 0 || fiche.polices_declarees.length > 0) && (
            <section className="rf-panel" aria-labelledby="rf-polices">
              <h2 id="rf-polices">Polices</h2>
              <dl className="rf-fonts">
                {Object.entries(fiche.polices).map(([role, famille]) => <div key={role}><dt>{ROLES[role] ?? role}</dt><dd>{famille}</dd></div>)}
              </dl>
              {fiche.polices_declarees.length > 0 && <p className="rf-caption">Chargées par le site : {fiche.polices_declarees.join(", ")}</p>}
            </section>
          )}
          {s && (
            <section className="rf-panel" aria-labelledby="rf-structure">
              <h2 id="rf-structure">Structure</h2>
              <ul className="rf-structure">
                {([["En-tête", s.entete], ["Héros", Boolean(s.heros)], ["Contenu principal", s.principal], ["Pied de page", s.pied]] as const).map(([nom, present]) => (
                  <li key={nom} className={present ? "is-present" : ""}>{present ? <Check size={16} /> : <X size={16} />}{nom}<span className="sr-only">{present ? " présent" : " absent"}</span></li>
                ))}
              </ul>
              {s.heros && <p className="rf-hero"><strong>{s.heros.titre}</strong>{s.heros.appel_action && <span>Appel à l'action : « {s.heros.appel_action} »</span>}</p>}
              <dl className="rf-counts tab-num">
                <div><dt>Sections</dt><dd>{s.sections.length}</dd></div><div><dt>Images</dt><dd>{s.images}</dd></div>
                <div><dt>Boutons</dt><dd>{s.boutons}</dd></div><div><dt>Liens de menu</dt><dd>{s.navigation}</dd></div>
              </dl>
            </section>
          )}
          {fiche.liens.length > 0 && (
            <section className="rf-panel" aria-labelledby="rf-liens">
              <h2 id="rf-liens">Liens sortants <span className="tab-num">{fiche.liens.length}</span></h2>
              <ul className="rf-links">
                {fiche.liens.slice(0, 14).map((l) => <li key={l.url}><a href={l.url} target="_blank" rel="noopener noreferrer"><span>{l.texte || hote(l.url)}</span><small>{hote(l.url)}</small></a></li>)}
              </ul>
            </section>
          )}
          <section className="rf-panel" aria-labelledby="rf-index">
            <h2 id="rf-index">Index</h2>
            <dl className="rf-counts tab-num">
              <div><dt>Passages</dt><dd>{fiche.index.fragments}</dd></div>
              <div><dt>Vecteurs</dt><dd>{fiche.index.vecteurs || "—"}</dd></div>
            </dl>
            <p className="rf-caption">{fiche.index.vecteurs ? `Modèle ${fiche.index.modele}, dimension ${fiche.index.dimension}` : "Recherche par mots. Les vecteurs sont optionnels et se recalculent à tout moment."}</p>
            <p className="rf-caption rf-hash" title={fiche.empreinte}>Empreinte {fiche.empreinte.slice(0, 16)}…</p>
          </section>
        </aside>
      </div>
    </section>
  );
}

function LigneSection({ s, actif, montrable, choisir }: { s: Section; actif: boolean; montrable: boolean; choisir: () => void }) {
  const contenu = <><span className="rf-level">{s.niveau ? `H${s.niveau}` : "—"}</span><span className="rf-section-text"><strong>{s.titre || "Introduction"}</strong><small>{s.extrait}</small></span></>;
  return (
    <li className={`niveau-${s.niveau}`}>
      {montrable ? <button type="button" aria-pressed={actif} onClick={choisir} title="Montrer cette section dans la capture">{contenu}</button> : <div className="rf-section-static">{contenu}</div>}
    </li>
  );
}
