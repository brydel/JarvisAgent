import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { AlertTriangle, ArrowUpRight, CheckCircle2, Copy, FileText, Globe, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import type { Source } from "../api";
import { ProductNav } from "../product/ProductNav";
import { useStudioNavigation } from "../product/routing";
import { ajouter, chercher, citation, dateCapture, EN_COURS, hote, LIBELLES, lister, recapturer, supprimer,
  type Filtres, type Liste, type Passage, type Recherche, type Reference } from "./api";
import { FicheReference } from "./FicheReference";
import "../styles/product.css";
import "./references.css";

const message = (e: unknown) => (e instanceof Error ? e.message : "Opération indisponible");
const ANTI_REBOND_MS = 140;

function lireUrl() {
  const p = new URLSearchParams(location.search);
  return { q: p.get("q") ?? "", ref: p.get("ref"), fragment: p.get("fragment") };
}
function ecrireUrl(valeurs: { q?: string; ref?: string | null; fragment?: string | null }, empiler = false) {
  const u = new URL(location.href);
  for (const [k, v] of Object.entries(valeurs)) { if (v) u.searchParams.set(k, v); else u.searchParams.delete(k); }
  if (empiler) history.pushState(null, "", u); else history.replaceState(null, "", u);
}

/** Texte avec ses plages surlignées (positions fournies par le serveur) : jamais de HTML injecté. */
export function Surligne({ texte, plages }: { texte: string; plages: [number, number][] }) {
  const morceaux: ReactNode[] = [];
  let curseur = 0;
  plages.forEach(([a, b], i) => {
    if (a < curseur || b > texte.length) return;
    morceaux.push(texte.slice(curseur, a), <mark key={i}>{texte.slice(a, b)}</mark>);
    curseur = b;
  });
  morceaux.push(texte.slice(curseur));
  return <>{morceaux}</>;
}

export type Avis = { texte: string; action?: { libelle: string; faire: () => void } } | null;

export default function ReferencesWorkspace({ source }: { source: Source }) {
  const demo = source.demo;
  const { aller } = useStudioNavigation();
  const initial = useMemo(lireUrl, []);
  const [q, setQ] = useState(initial.q);
  const [ouverte, setOuverte] = useState<{ id: string; fragment: string | null; section?: string } | null>(initial.ref ? { id: initial.ref, fragment: initial.fragment } : null);
  const [filtres, setFiltres] = useState<Filtres>({ collection: null, etiquette: null });
  const [liste, setListe] = useState<Liste | null>(null);
  const [erreur, setErreur] = useState("");
  const [recherche, setRecherche] = useState<Recherche | null>(null);
  const [enRecherche, setEnRecherche] = useState(false);
  const [erreurRecherche, setErreurRecherche] = useState("");
  const [avis, setAvis] = useState<Avis>(null);
  const [version, setVersion] = useState(0);  // incrémenté après une écriture : liste et recherche se rechargent
  const champ = useRef<HTMLInputElement>(null);
  const resultats = useRef<HTMLOListElement>(null);

  const charger = useCallback(async (signal?: AbortSignal) => {
    try { const l = await lister(demo, filtres, signal); if (!signal?.aborted) { setListe(l); setErreur(""); } }
    catch (e) { if (!signal?.aborted) setErreur(message(e)); }
  }, [demo, filtres]);
  useEffect(() => { const c = new AbortController(); void charger(c.signal); return () => c.abort(); }, [charger, version]);
  const enCours = liste?.references.some((r) => EN_COURS.includes(r.statut)) ?? false;
  useEffect(() => {  // une capture tourne : on suit son état sans que l'utilisateur ait à recharger
    if (!enCours) return;
    const t = window.setInterval(() => { if (document.visibilityState === "visible") void charger(); }, 1200);
    return () => window.clearInterval(t);
  }, [enCours, charger]);
  useEffect(() => {
    const voir = () => { if (document.visibilityState === "visible") void charger(); };
    document.addEventListener("visibilitychange", voir);
    return () => document.removeEventListener("visibilitychange", voir);
  }, [charger]);

  // Recherche à la frappe : anti-rebond, annulation de la requête précédente, résultats précédents gardés à l'écran.
  const question = q.trim();
  useEffect(() => {
    ecrireUrl({ q: question });
    if (question.length < 2) { setRecherche(null); setEnRecherche(false); setErreurRecherche(""); return; }
    setEnRecherche(true);
    const c = new AbortController();
    const t = window.setTimeout(() => {
      chercher(demo, question, filtres, c.signal)
        .then((r) => { if (!c.signal.aborted) { setRecherche(r); setErreurRecherche(""); } })
        .catch((e) => { if (!c.signal.aborted) setErreurRecherche(message(e)); })
        .finally(() => { if (!c.signal.aborted) setEnRecherche(false); });
    }, ANTI_REBOND_MS);
    return () => { window.clearTimeout(t); c.abort(); };
  }, [question, filtres, demo, version]);

  useEffect(() => {
    const retour = () => { const u = lireUrl(); setOuverte(u.ref ? { id: u.ref, fragment: u.fragment } : null); setQ(u.q); };
    window.addEventListener("popstate", retour);
    return () => window.removeEventListener("popstate", retour);
  }, []);
  useEffect(() => {
    const touche = (e: globalThis.KeyboardEvent) => {
      const cible = e.target as HTMLElement | null;
      const saisie = cible && (cible.tagName === "INPUT" || cible.tagName === "TEXTAREA" || cible.isContentEditable);
      if (e.key === "/" && !saisie && !e.metaKey && !e.ctrlKey && !ouverte) { e.preventDefault(); champ.current?.focus(); }
    };
    window.addEventListener("keydown", touche);
    return () => window.removeEventListener("keydown", touche);
  }, [ouverte]);
  useEffect(() => { if (!avis) return; const t = window.setTimeout(() => setAvis(null), 6000); return () => window.clearTimeout(t); }, [avis]);

  const ouvrir = (id: string, fragment: string | null = null, section?: string) => { ecrireUrl({ ref: id, fragment }, true); setOuverte({ id, fragment, section }); };
  const fermer = () => { ecrireUrl({ ref: null, fragment: null }, true); setOuverte(null); };
  const rafraichir = () => setVersion((v) => v + 1);
  const retirer = async (r: Reference) => {
    try {
      await supprimer(r.id);
      rafraichir();
      setAvis({ texte: `« ${r.titre} » retirée de la bibliothèque`, action: { libelle: "Annuler", faire: () => { void supprimer(r.id, true).then(rafraichir); setAvis(null); } } });
    } catch (e) { setAvis({ texte: message(e) }); }
  };
  const relancer = async (r: Reference) => { try { await recapturer(r.id); rafraichir(); } catch (e) { setAvis({ texte: message(e) }); } };
  const copier = async (p: Passage) => {
    try { await navigator.clipboard.writeText(citation(p)); setAvis({ texte: "Citation copiée, avec sa source et sa date de capture" }); }
    catch { setAvis({ texte: "Copie impossible dans ce navigateur" }); }
  };
  const fleches = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const boutons = Array.from(resultats.current?.querySelectorAll<HTMLButtonElement>(".rf-result-open") ?? []);
    if (!boutons.length) return;
    const i = boutons.indexOf(document.activeElement as HTMLButtonElement);
    e.preventDefault();
    if (e.key === "ArrowUp" && i <= 0) champ.current?.focus();
    else boutons[Math.min(boutons.length - 1, e.key === "ArrowDown" ? i + 1 : i - 1)]?.focus();
  };

  const enModeRecherche = question.length >= 2;
  const vide = liste !== null && liste.total === 0;
  return (
    <div className="product-app">
      <ProductNav />
      <main className="product-main" id="contenu-produit">
        {ouverte ? (
          <FicheReference key={ouverte.id} id={ouverte.id} sectionInitiale={ouverte.section} demo={demo} espace={source.espace} retour={fermer}
            notifier={(texte) => setAvis({ texte })} apresChangement={rafraichir}
            apresPose={(objet) => aller("board", { carte: objet })}
            apresSuppression={(titre, id) => { fermer(); rafraichir(); setAvis({ texte: `« ${titre} » retirée de la bibliothèque`, action: { libelle: "Annuler", faire: () => { void supprimer(id, true).then(rafraichir); setAvis(null); } } }); }} />
        ) : (
          <section className="p-page rf-page" aria-labelledby="rf-titre">
            <div className="p-page-heading">
              <div>
                <h1 id="rf-titre">Références</h1>
                <p>Capture un site, retrouve-le par ses mots, sa palette ou ses polices, et pose-le sur le Board. Chaque passage est cité avec sa source, jamais résumé. La bibliothèque reste sur ton poste et la recherche fonctionne sans aucun fournisseur d'IA.</p>
              </div>
              {liste && <Moteur liste={liste} />}
            </div>

            <label className={`rf-search ${enRecherche ? "is-busy" : ""}`}>
              <Search size={16} strokeWidth={1.5} aria-hidden />
              <input ref={champ} type="search" value={q} placeholder="Rechercher dans les références"
                aria-label="Rechercher dans les références" aria-controls="rf-resultats" autoComplete="off" spellCheck={false}
                onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape" && q) { e.preventDefault(); setQ(""); } else fleches(e); }} />
              {enRecherche && <span className="rf-spinner" role="status" aria-label="Recherche en cours" />}
              {q ? <button type="button" className="rf-clear" onClick={() => { setQ(""); champ.current?.focus(); }} aria-label="Effacer la recherche"><X size={16} /></button> : <kbd>/</kbd>}
            </label>

            {liste && liste.total > 0 && <Facettes liste={liste} filtres={filtres} setFiltres={setFiltres} />}
            {erreur && <div className="p-error" role="alert"><span>{erreur}</span><button className="p-button p-quiet" onClick={() => void charger()}><RefreshCw size={16} />Réessayer</button></div>}

            {enModeRecherche ? (
              <div id="rf-resultats" aria-busy={enRecherche} onKeyDown={fleches}>
                <p className="rf-count" role="status" aria-live="polite">
                  {erreurRecherche ? "" : recherche ? `${recherche.resultats.length} passage${recherche.resultats.length > 1 ? "s" : ""} pour « ${recherche.question} »${recherche.mode === "hybride" ? " · mots et vecteurs fusionnés" : recherche.vecteurs === "indisponible" ? " · vecteurs indisponibles, recherche par mots" : ""}` : "Recherche"}
                </p>
                {erreurRecherche && <div className="p-error" role="alert"><span>{erreurRecherche}</span><button className="p-button p-quiet" onClick={rafraichir}><RefreshCw size={16} />Réessayer</button></div>}
                {recherche && !erreurRecherche && (recherche.resultats.length ? (
                  <ol className={`rf-results ${enRecherche ? "is-stale" : ""}`} ref={resultats}>
                    {recherche.resultats.map((p) => <ResultatPassage key={p.fragment_id} p={p} hybride={recherche.mode === "hybride"} ouvrir={() => ouvrir(p.reference_id, p.fragment_id, p.section)} copier={() => void copier(p)} />)}
                  </ol>
                ) : (
                  <div className="p-empty rf-empty"><h3>Aucun passage ne répond à cette question</h3>
                    <p>La recherche par mots trouve ce qui est écrit dans tes captures. Essaie un terme présent sur le site{filtres.collection !== null || filtres.etiquette ? ", ou retire le filtre actif" : ""}.</p>
                    {(filtres.collection !== null || filtres.etiquette) && <button className="p-button p-quiet" onClick={() => setFiltres({ collection: null, etiquette: null })}>Chercher partout</button>}
                  </div>
                ))}
                {!recherche && !erreurRecherche && <SqueletteResultats />}
              </div>
            ) : (
              <>
                <FormulaireAjout demo={demo} collections={liste?.collections.map((c) => c.nom).filter(Boolean) ?? []} captureDisponible={liste?.moteur.capture ?? true}
                  apres={(r, deja) => { rafraichir(); setAvis({ texte: deja ? "Ce site est déjà dans cette collection" : r.type === "site" ? `Capture de ${hote(r.source)} lancée : bureau et mobile` : `« ${r.titre} » indexé` }); }} />
                {!liste && !erreur && <SqueletteGrille />}
                {vide && (
                  <div className="p-empty rf-empty"><h3>Aucune référence dans la bibliothèque</h3>
                    <p>Colle l'adresse d'un site que tu admires. Jarvis en garde les captures bureau et mobile, le texte par sections, la palette et les polices, sur ton poste.</p></div>
                )}
                {liste && !vide && !liste.references.length && (
                  <div className="p-empty rf-empty"><h3>Rien dans ce filtre</h3><p>Aucune référence ne porte cette collection et cette étiquette à la fois</p>
                    <button className="p-button p-quiet" onClick={() => setFiltres({ collection: null, etiquette: null })}>Tout afficher</button></div>
                )}
                {liste && liste.references.length > 0 && (
                  <ul className="rf-grid" aria-label="Références">
                    {liste.references.map((r) => <li key={r.id}><Carte r={r} ouvrir={() => ouvrir(r.id)} relancer={() => void relancer(r)} retirer={() => void retirer(r)} demo={demo} /></li>)}
                  </ul>
                )}
              </>
            )}
          </section>
        )}
      </main>
      {avis && (
        <div className="p-feedback rf-feedback" role="status"><CheckCircle2 size={16} /><span>{avis.texte}</span>
          {avis.action && <button className="rf-feedback-action" onClick={avis.action.faire}>{avis.action.libelle}</button>}</div>
      )}
    </div>
  );
}

function Moteur({ liste }: { liste: Liste }) {
  const m = liste.moteur;
  return (
    <dl className="rf-engine" aria-label="Moteur de recherche">
      <div><dt>Références</dt><dd className="tab-num">{liste.total}</dd></div>
      <div><dt>Mots</dt><dd title={m.mots === "fts5" ? "Index BM25 de SQLite (FTS5), sans accents, avec préfixes" : "Classement BM25 calculé par Jarvis (index FTS5 indisponible)"}>BM25 local</dd></div>
      <div><dt>Vecteurs</dt><dd title={m.vecteurs ? `${m.fragments_vectorises} fragments vectorisés` : "Optionnel : un modèle local (Ollama) peut être branché dans les réglages"}>{m.vecteurs ? m.modele : "désactivés"}</dd></div>
    </dl>
  );
}

function Facettes({ liste, filtres, setFiltres }: { liste: Liste; filtres: Filtres; setFiltres: (f: Filtres) => void }) {
  return (
    <div className="rf-facets">
      <div className="rf-chips" role="group" aria-label="Collections">
        <button type="button" aria-pressed={filtres.collection === null} onClick={() => setFiltres({ ...filtres, collection: null })}>Toutes<span className="tab-num">{liste.total}</span></button>
        {liste.collections.map((c) => (
          <button type="button" key={c.nom || "∅"} aria-pressed={filtres.collection === c.nom} onClick={() => setFiltres({ ...filtres, collection: filtres.collection === c.nom ? null : c.nom })}>
            {c.nom || "Sans collection"}<span className="tab-num">{c.n}</span></button>
        ))}
      </div>
      {liste.etiquettes.length > 0 && (
        <div className="rf-chips rf-tags" role="group" aria-label="Étiquettes">
          {liste.etiquettes.slice(0, 14).map((e) => (
            <button type="button" key={e.nom} aria-pressed={filtres.etiquette === e.nom} onClick={() => setFiltres({ ...filtres, etiquette: filtres.etiquette === e.nom ? null : e.nom })}>#{e.nom}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function FormulaireAjout({ demo, collections, captureDisponible, apres }: { demo: boolean; collections: string[]; captureDisponible: boolean; apres: (r: Reference, deja: boolean) => void }) {
  const [mode, setMode] = useState<"site" | "texte">("site");
  const [url, setUrl] = useState("");
  const [texte, setTexte] = useState("");
  const [titre, setTitre] = useState("");
  const [collection, setCollection] = useState("");
  const [etiquettes, setEtiquettes] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState("");
  const soumettre = async (e: FormEvent) => {
    e.preventDefault();
    if (envoi) return;
    setEnvoi(true); setErreur("");
    try {
      const tags = etiquettes.split(",").map((t) => t.trim()).filter(Boolean);
      const r = await ajouter(mode === "site" ? { url: url.trim(), collection, etiquettes: tags } : { texte, titre, collection, etiquettes: tags });
      setUrl(""); setTexte(""); setTitre("");
      apres(r, Boolean(r.deja));
    } catch (err) { setErreur(message(err)); }
    finally { setEnvoi(false); }
  };
  const pret = mode === "site" ? url.trim().length > 3 : texte.trim().length > 0;
  return (
    <form className="rf-add" onSubmit={soumettre} aria-label="Ajouter une référence">
      <div className="rf-add-mode" role="group" aria-label="Type de référence">
        <button type="button" aria-pressed={mode === "site"} onClick={() => setMode("site")}><Globe size={16} />Site</button>
        <button type="button" aria-pressed={mode === "texte"} onClick={() => setMode("texte")}><FileText size={16} />Texte</button>
      </div>
      {mode === "site" ? (
        <input className="rf-add-url" name="url" inputMode="url" autoComplete="off" spellCheck={false} placeholder="https://exemple.com" aria-label="Adresse du site à capturer"
          value={url} onChange={(e) => setUrl(e.target.value)} disabled={demo} />
      ) : (
        <div className="rf-add-texte">
          <input name="titre" placeholder="Titre" aria-label="Titre du texte" value={titre} onChange={(e) => setTitre(e.target.value)} disabled={demo} />
          <textarea name="texte" rows={4} placeholder="Texte ou Markdown" aria-label="Texte à indexer"
            value={texte} onChange={(e) => setTexte(e.target.value)} disabled={demo} />
        </div>
      )}
      <input name="collection" list="rf-collections" placeholder="Collection" aria-label="Collection" value={collection} onChange={(e) => setCollection(e.target.value)} disabled={demo} maxLength={80} />
      <datalist id="rf-collections">{collections.map((c) => <option key={c} value={c} />)}</datalist>
      <input name="etiquettes" placeholder="Étiquettes, séparées par des virgules" aria-label="Étiquettes, séparées par des virgules" value={etiquettes} onChange={(e) => setEtiquettes(e.target.value)} disabled={demo} />
      <button className="p-button p-primary" type="submit" disabled={demo || envoi || !pret}><Plus size={16} />{envoi ? "Envoi…" : mode === "site" ? "Capturer" : "Indexer"}</button>
      {mode === "texte" && <p className="rf-add-note">Les titres #, ## et ### deviennent des sections</p>}
      {demo && <p className="rf-add-note">Démonstration : sites fictifs, la capture est désactivée</p>}
      {!demo && mode === "site" && !captureDisponible && <p className="rf-add-note is-warning"><AlertTriangle size={16} />Chromium n'est pas installé sur ce poste : <code>./install.sh --studio</code>. Les textes restent indexables.</p>}
      {erreur && <p className="rf-add-note is-error" role="alert">{erreur}</p>}
    </form>
  );
}

function Carte({ r, ouvrir, relancer, retirer, demo }: { r: Reference; ouvrir: () => void; relancer: () => void; retirer: () => void; demo: boolean }) {
  const enCours = EN_COURS.includes(r.statut);
  const polices = Array.from(new Set(Object.values(r.polices))).slice(0, 2);
  return (
    <article className={`rf-card is-${r.statut}`}>
      <button type="button" className="rf-card-open" onClick={ouvrir} aria-label={`Ouvrir la fiche de ${r.titre}${enCours ? ` (${LIBELLES[r.statut]})` : ""}`}>
        <div className="rf-card-preview">
          {r.vignette_url && !enCours ? <img src={r.vignette_url} alt="" loading="lazy" decoding="async" />
            : enCours ? <div className="rf-card-wait"><span className="rf-spinner" /><strong>{LIBELLES[r.statut]}</strong><small>{r.statut === "indexation" ? "Découpage et index des passages" : "Bureau 1440 px, puis mobile 390 px"}</small></div>
            : r.statut === "echec" ? <div className="rf-card-wait is-error"><AlertTriangle size={16} /><strong>Capture impossible</strong><small>{r.raison}</small></div>
            : <div className="rf-card-wait"><FileText size={16} /></div>}
          {r.palette.length > 0 && !enCours && <div className="rf-strip" aria-hidden>{r.palette.slice(0, 6).map((c) => <i key={c.hex} style={{ background: c.hex, flexGrow: Math.max(c.part, 0.04) }} />)}</div>}
        </div>
        <div className="rf-card-body">
          <h3>{r.titre}</h3>
          <p className="rf-card-source">{r.type === "site" ? hote(r.url || r.source) : r.type === "carte" ? "Carte du Board" : "Texte déposé"}<span>{dateCapture(r.capture_le ?? r.cree)}</span></p>
          {polices.length > 0 && <p className="rf-card-fonts"><span aria-hidden>Aa</span>{polices.join(" · ")}</p>}
          <div className="rf-card-meta">
            {r.collection && <span className="rf-collection">{r.collection}</span>}
            {r.etiquettes.slice(0, 3).map((e) => <span key={e} className="rf-tag">#{e}</span>)}
          </div>
        </div>
      </button>
      {r.statut === "echec" && !demo && (
        <div className="rf-card-actions">
          <button type="button" className="p-button p-quiet" onClick={relancer}><RefreshCw size={16} />Relancer</button>
          <button type="button" className="p-button p-quiet" onClick={retirer} aria-label={`Retirer ${r.titre}`}><Trash2 size={16} />Retirer</button>
        </div>
      )}
    </article>
  );
}

function ResultatPassage({ p, hybride, ouvrir, copier }: { p: Passage; hybride: boolean; ouvrir: () => void; copier: () => void }) {
  const c = p.citation;
  // Renvoi vers la zone de la capture : la page entière, cadrée sur la section d'où vient le passage.
  const cadre = c.capture_url ? { backgroundImage: `url("${c.capture_url}")`, backgroundSize: "100% auto",
    backgroundPosition: c.zone ? `0 ${-Math.max(0, c.zone.y - 12) * (220 / 1440)}px` : "0 0" } : undefined;
  return (
    <li className="rf-result">
      <div className="rf-result-zone" style={cadre} aria-hidden>{!c.capture_url && <FileText size={16} />}</div>
      <div className="rf-result-body">
        <button type="button" className="rf-result-open" onClick={ouvrir}>
          <strong>{c.titre}</strong>{c.section && <span className="rf-section"><Surligne texte={c.section} plages={p.section_surlignages ?? []} /></span>}
        </button>
        <blockquote><Surligne texte={p.extrait.texte} plages={p.extrait.surlignages} /></blockquote>
        <footer>
          {c.url ? <a href={c.url} target="_blank" rel="noopener noreferrer">{hote(c.url)}<ArrowUpRight size={16} /></a> : <span>{c.type === "carte" ? "Carte du Board" : "Texte déposé"}</span>}
          <span>capturé le {dateCapture(c.capture_le)}</span>
          {c.collection && <span className="rf-collection">{c.collection}</span>}
          {hybride && <span className="rf-ranks tab-num" title="Rang dans chaque moteur avant la fusion RRF">{p.rangs.mots ? `mots n° ${p.rangs.mots}` : "hors mots"} · {p.rangs.vecteurs ? `vecteurs n° ${p.rangs.vecteurs}` : "hors vecteurs"}</span>}
          <button type="button" className="rf-copy" onClick={copier}><Copy size={16} />Copier la citation</button>
        </footer>
      </div>
    </li>
  );
}

function SqueletteGrille() {
  return <ul className="rf-grid" aria-hidden>{[0, 1, 2].map((i) => <li key={i}><div className="rf-card rf-skeleton"><div className="rf-card-preview" /><div className="rf-card-body"><i /><i /></div></div></li>)}</ul>;
}
function SqueletteResultats() {
  return <ol className="rf-results" aria-hidden>{[0, 1, 2].map((i) => <li key={i} className="rf-result rf-skeleton"><div className="rf-result-zone" /><div className="rf-result-body"><i /><i /><i /></div></li>)}</ol>;
}
