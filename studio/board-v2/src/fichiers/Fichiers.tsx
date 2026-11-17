import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ChangeEvent, type Ref } from "react";
import { ArrowDownLeft, ArrowRight, ArrowUpRight, ChevronLeft, ChevronRight, Database, FileText, Folder, History,
  LayoutGrid, Link2, List, Plus, Radio, RefreshCw, Router, Workflow, X } from "lucide-react";
import { SourceReelle, type Source } from "../api";
import type { EtatBoard, EspaceBoard, ObjetBoard, StyleLien } from "../types";
import { dateCourte, dateHeure, duree, LIBELLE_TYPE, taille } from "../lib/format";
import { ProductNav } from "../product/ProductNav";
import { VitrineStudio } from "../product/VitrineStudio";
import { useStudioNavigation } from "../product/routing";
import { useDispositionAnimee, useZoneFondu } from "../ui/fondu";
import { SpotlightCard } from "../ui/react-bits/SpotlightCard";
import { ApercuFichier } from "./ApercuFichier";
import { EditeurNote } from "../components/EditeurNote";
import { ciblesWiki, resoudreWiki } from "../lib/wikiliens";
import { CarteGraphe, Miniature } from "./CarteGraphe";
import { ContexteCarte, useContexteCarte } from "./ContexteCarte";
import { MemoireFichier } from "./MemoireFichier";
import { InspecteurReferences } from "./GrapheReferences";
import { useReferencesGraphe } from "./useReferencesGraphe";
import { useGrapheGlobal } from "./useGrapheGlobal";
import { sourceProjetDemo } from "./global-demo";
import type { GroupeGraphe, SessionGraphe } from "./global-donnees";
import { CommandesJournal, FicheEntreeJournal, ListeJournal } from "./JournalMemoire";
import { NATURES_MEMOIRE, type NatureMemoire } from "./journal-donnees";
import { autre, construire, estFichier, estNote, LIBELLES, regrouperRelations, sousGraphe, titreDe, TYPES,
  type Disposition, type Entite, type Graphe } from "./graphe";
import "../styles/product.css";
import "./fichiers.css";

const TAILLE_PAGE = 28;
const TYPE_LIENS: StyleLien[] = ["inspire", "alimente", "utilise", "depend", "defaut"];
const TYPES_TEXTE = /\.(md|txt|csv|json|srt|vtt)$/i;
const mot = (x: string) => x.toLocaleLowerCase("fr").normalize("NFD").replace(/\p{Diacritic}/gu, "");
const message = (e: unknown) => e instanceof Error ? e.message : "L’opération a échoué.";
const lireSelection = () => {
  const p = new URLSearchParams(location.search);
  return p.get("observation") || p.get("ref") || p.get("fichier");
};
const lireJournal = () => new URLSearchParams(location.search).get("journal") === "1";

export default function Fichiers({ source }: { source: Source }) {
  const { aller } = useStudioNavigation();
  const [board, setBoard] = useState<EtatBoard | null>(null);
  const [espaces, setEspaces] = useState<EspaceBoard[]>([]);
  const [erreur, setErreur] = useState("");
  const [notice, setNotice] = useState("");
  const [recherche, setRecherche] = useState("");
  const [type, setType] = useState("");
  const [journalActif, setJournalActif] = useState(lireJournal);
  const [rechercheJournal, setRechercheJournal] = useState("");
  const [natureJournal, setNatureJournal] = useState<NatureMemoire | "">("");
  const references = useReferencesGraphe(source);
  const actualiserReferences = useRef(references.actualiser);
  actualiserReferences.current = references.actualiser;
  const [affichage, setAffichage] = useState<Disposition | "liste">("constellation");
  const [scene, fondreScene] = useZoneFondu<HTMLElement>();
  const changerAffichage = useDispositionAnimee(affichage, setAffichage, fondreScene);
  const dernierGraphe = useRef<Disposition>("constellation");
  const graphe = journalActif || affichage !== "liste";
  const disposition = affichage === "liste" ? dernierGraphe.current : affichage;
  const changerGraphe = (disposition: Disposition) => {
    dernierGraphe.current = disposition;
    changerAffichage(disposition);
  };
  const [demande, setDemande] = useState(lireSelection);
  const [sessionChoisie, setSessionChoisie] = useState(() => new URLSearchParams(location.search).get("session"));
  const [projet, setProjet] = useState("");
  const global = useGrapheGlobal(source, sessionChoisie || demande);
  const journal = {
    nature: natureJournal, filtrer: setNatureJournal,
    entrees: global.entrees.filter((e) => !natureJournal || e.nature === natureJournal),
    charge: global.charge, erreur: global.erreur || undefined, page: global.page,
    actualiser: global.actualiser, reessayer: global.actualiser, precedent: undefined, suivant: global.suivant,
  };
  const actualiserGlobal = useRef(global.actualiser);
  actualiserGlobal.current = global.actualiser;
  const [focus, setFocus] = useState<string | null>(null);
  const [profondeur, setProfondeur] = useState(1);
  const [page, setPage] = useState(1);
  const [envoi, setEnvoi] = useState(false);
  const [relier, setRelier] = useState(false);
  const [graphePrepare, setGraphePrepare] = useState(false);
  const fichier = useRef<HTMLInputElement>(null);
  const inspecteur = useRef<HTMLElement>(null);
  const centrer = useRef<((id: string) => void) | null>(null);
  const rapprochement = useRef<string | null>(null);
  const version = useRef(0);
  const actif = useRef(false);

  const charger = useCallback(async () => {
    const v = ++version.current;
    try {
      const b = await source.charger();
      if (actif.current && v === version.current) { setBoard(b); setErreur(""); actualiserGlobal.current(); }
    } catch (e) { if (actif.current && v === version.current) setErreur(message(e)); }
  }, [source]);

  useEffect(() => {
    actif.current = true;
    void charger();
    void source.espaces().then((r) => { if (actif.current) setEspaces(r); }, () => {});
    const flux = source.demo ? null : new EventSource("/api/flux?apres=fin");
    let timer = 0;
    let sourcesModifiees = false;
    if (flux) flux.onmessage = (e) => {
      if (!/board_|reference_|mission_|tache_|runtime|agent_/.test(e.data)) return;
      sourcesModifiees ||= /reference_/.test(e.data);
      if (timer || document.hidden) return;
      timer = window.setTimeout(() => {
        timer = 0; void charger();
        if (sourcesModifiees) actualiserReferences.current();
        sourcesModifiees = false;
      }, 350);
    };
    const visible = () => {
      if (!document.hidden && !source.demo) { void charger(); actualiserReferences.current(); }
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      actif.current = false; version.current++; flux?.close(); window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [charger, source]);
  useEffect(() => {
    const attendue = new URLSearchParams(location.search).get("ref");
    const sourcePrete = !attendue || references.referenceChargee?.id === attendue || !!references.erreur;
    if ((board || erreur) && sourcePrete && !references.charge && !references.chargeReference && !global.charge && !global.chargeCible) setGraphePrepare(true);
  }, [board, erreur, references.charge, references.chargeReference, references.referenceChargee, references.erreur, global.charge, global.chargeCible]);
  useEffect(() => {
    const retour = () => {
      const selection = lireSelection();
      rapprochement.current = selection;
      setDemande(selection); setSessionChoisie(new URLSearchParams(location.search).get("session")); setJournalActif(lireJournal()); setFocus(null);
    };
    window.addEventListener("popstate", retour);
    return () => window.removeEventListener("popstate", retour);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const modele = useMemo(() => {
    if (!global.donnees && !references.references.length) return null;
    return construire({ espace: "global", objets: global.objets, liens: global.liens }, global.entrees, references.references, global.sessions);
  }, [global.donnees, global.objets, global.liens, global.entrees, global.sessions, references.references]);
  const modeleAffiche = useMemo(() => modele && projet ? { ...modele,
    groupes: modele.groupes?.filter((g) => g.projet === projet || global.sessions.some((s) => s.id === g.id && s.projets.includes(projet))),
  } : modele, [modele, projet, global.sessions]);
  const fichiers = useMemo(() => {
    const q = mot(recherche.trim());
    return (modele?.fichiers ?? []).filter(({ objet: o, titre }) => (!type || o.type === type) && (!q ||
      mot([titre, o.asset?.nom, o.meta.description, ...(o.meta.tags ?? [])].filter(Boolean).join(" ")).includes(q)));
  }, [modele, recherche, type]);
  const recents = useMemo(() => [...fichiers].sort((a, b) => b.objet.maj - a.objet.maj).slice(0, 8), [fichiers]);
  const entreesJournal = useMemo(() => {
    const q = mot(rechercheJournal.trim());
    return q ? journal.entrees.filter((e) => mot([e.mission_titre, e.titre, e.detail, e.auteur].filter(Boolean).join(" ")).includes(q)) : journal.entrees;
  }, [journal.entrees, rechercheJournal]);
  const journalVisible = useMemo(() => {
    const ids = new Set(entreesJournal.map((e) => e.id));
    return modele?.journal.filter((e) => ids.has(e.memoire.id)) ?? [];
  }, [modele, entreesJournal]);
  const racines = useMemo(() => {
    const q = mot(recherche.trim());
    return (modele?.racines ?? []).filter((e) => {
      const format = type === "reference" ? !!e.sourceRag && !e.observation
        : type === "observation" ? !!e.observation : type === "memoire" ? !!e.memoire : !type || e.type === type;
      const texte = [e.titre, e.observation?.texte, e.sourceRag?.collection, e.memoire?.detail,
        e.objet?.asset?.nom, e.objet?.meta.description, ...(e.objet?.meta.tags ?? [])].filter(Boolean).join(" ");
      const dansProjet = !projet || e.projet === projet || e.objet?.espace === projet || !!e.reference ||
        e.sessionIds?.some((id) => global.sessions.some((s) => s.id === id && s.projets.includes(projet)));
      return format && dansProjet && (!q || mot(texte).includes(q));
    });
  }, [modele, recherche, type, projet, global.sessions]);
  const demandee = modele?.entites.get(demande ?? "");
  const sessionActive = global.sessions.find((s) => s.id === sessionChoisie);
  const groupeActif = modele?.groupes?.find((g) => g.id === sessionChoisie);
  const selection = groupeActif ? undefined : demandee ?? (journalActif ? journalVisible[0] : graphe ? racines[0] : fichiers[0]);
  const sourceSelection = useMemo(() => {
    const espace = selection?.objet?.espace;
    if (!espace || espace === source.espace) return source;
    return source.demo ? sourceProjetDemo(source, espace) : new SourceReelle(espace);
  }, [source, selection?.objet?.espace]);
  const referenceSelection = selection?.reference;
  useEffect(() => {
    const reference = referenceSelection || new URLSearchParams(location.search).get("ref");
    if (reference) void references.chargerReference(reference);
  }, [referenceSelection, references.chargerReference]);
  const contexte = useContexteCarte(modele, selection?.id, source.demo);
  const projection = useMemo(() => modele ? sousGraphe(modele, racines,
    focus && modele.entites.has(focus) ? focus : null, profondeur, journalActif, true, selection?.id ?? null)
    : null, [modele, racines, journalActif, focus, profondeur, selection?.id]);
  useEffect(() => {
    const id = rapprochement.current;
    if (!id || !graphePrepare || !projection?.ids.includes(id)) return;
    const image = requestAnimationFrame(() => {
      centrer.current?.(id);
      rapprochement.current = null;
    });
    return () => cancelAnimationFrame(image);
  }, [projection, graphePrepare]);

  const choisir = (id: string, rapprocher = false) => {
    setDemande(id); setSessionChoisie(null);
    const u = new URL(location.href);
    const e = modele?.entites.get(id);
    u.searchParams.delete("session"); u.searchParams.delete("sources"); u.searchParams.delete("fichier");
    u.searchParams.delete("ref"); u.searchParams.delete("observation");
    if (e?.reference) {
      u.searchParams.set("ref", e.reference);
      if (e.observation) u.searchParams.set("observation", id);
    } else u.searchParams.set("fichier", id);
    history.replaceState(history.state, "", u);
    if (rapprocher) rapprochement.current = id;
  };
  const effacerSelection = () => {
    setDemande(null); setSessionChoisie(null);
    const u = new URL(location.href);
    for (const cle of ["fichier", "ref", "observation", "sources", "session"]) u.searchParams.delete(cle);
    history.replaceState(history.state, "", u);
  };
  const choisirSession = (id: string) => {
    setSessionChoisie(id); setDemande(null);
    const u = new URL(location.href);
    for (const cle of ["fichier", "ref", "observation", "sources", "session"]) u.searchParams.delete(cle);
    u.searchParams.set("session", id);
    history.replaceState(history.state, "", u);
  };
  const ouvrirApercu = (id: string) => {
    choisir(id, true);
    requestAnimationFrame(() => inspecteur.current?.focus());
  };
  const changerMode = (mode: "journal" | "graphe" | "liste") => {
    if ((mode === "journal") !== journalActif) {
      const u = new URL(location.href);
      if (mode === "journal") u.searchParams.set("journal", "1");
      else u.searchParams.delete("journal");
      for (const cle of ["fichier", "ref", "observation", "sources", "session"]) u.searchParams.delete(cle);
      history.replaceState(history.state, "", u);
      setDemande(null);
      setSessionChoisie(null);
      setFocus(null);
      setJournalActif(mode === "journal");
    }
    if (mode === "liste") {
      if (type && !TYPES.some((format) => format === type)) setType("");
      if (selection?.reference || selection?.memoire || !selection?.objet || !estFichier(selection.objet)) {
        setDemande(null);
        const u = new URL(location.href);
        for (const cle of ["fichier", "ref", "observation", "sources", "session"]) u.searchParams.delete(cle);
        history.replaceState(history.state, "", u);
      }
    }
    if (mode !== "journal") changerAffichage(mode === "liste" ? "liste" : dernierGraphe.current);
  };
  const ouvrirSources = (ref?: string) => {
    if (!ref) return;
    setType(""); setRecherche(""); setFocus(null); changerAffichage(dernierGraphe.current);
    choisir(ref, true);
    void references.chargerReference(ref);
  };
  const ouvrirReference = (ref: string, fragment?: string) => aller("references", fragment ? { ref, fragment } : { ref });
  const filtrer = () => {
    setPage(1); setFocus(null); setDemande(null); setSessionChoisie(null);
    const u = new URL(location.href);
    for (const cle of ["fichier", "ref", "observation", "sources", "session"]) u.searchParams.delete(cle);
    history.replaceState(history.state, "", u);
  };
  const importer = async (e: ChangeEvent<HTMLInputElement>) => {
    const original = e.target.files?.[0];
    e.target.value = "";
    if (!original || envoi) return;
    setEnvoi(true); setErreur("");
    try {
      const textuel = TYPES_TEXTE.test(original.name);
      const contenu = textuel ? await original.slice(0, 100_001).text() : "";
      if (textuel && (original.size > 100_000 || contenu.length > 24_000 || !contenu.trim())) {
        throw new Error("Le document doit contenir de 1 à 24 000 caractères.");
      }
      const asset = textuel ? null : await source.televerser(original);
      const x = board?.objets.reduce((max, o) => Math.max(max, o.x + o.largeur), 110) ?? 110;
      const id = await source.creer({ type: asset?.famille ?? "document", contenu, asset_id: asset?.id, meta: { titre: original.name },
        x: x + 56, y: 140, largeur: 372, hauteur: asset?.famille === "audio" ? 172 : 256, analyser: false });
      filtrer(); setType(""); setRecherche(""); choisir(id); setNotice("Fichier ajouté à ce Board.");
      await charger();
    } catch (e) { setErreur(message(e)); }
    finally { setEnvoi(false); }
  };
  const changerEspace = (espace: string) => {
    const u = new URL(location.href);
    u.searchParams.set("espace", espace);
    for (const cle of ["fichier", "ref", "observation", "sources", "session"]) u.searchParams.delete(cle);
    location.assign(u);
  };
  const totalPages = Math.max(1, Math.ceil(fichiers.length / TAILLE_PAGE));
  const pageActive = Math.min(page, totalPages);
  const ignorer = !!projection && racines.length > projection.ids.length && !focus;

  const nombreNotes = fichiers.filter(({ objet }) => estNote(objet)).length;
  const nombreFichiers = fichiers.length - nombreNotes;
  const compte = [nombreFichiers || !nombreNotes ? `${nombreFichiers} fichier${nombreFichiers === 1 ? "" : "s"}` : "",
    nombreNotes ? `${nombreNotes} note${nombreNotes === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · ");

  return <div className="product-app">
    <ProductNav recherche={journalActif ? rechercheJournal : recherche} setRecherche={(q) => {
      if (journalActif) setRechercheJournal(q); else setRecherche(q);
      filtrer();
    }} />
    <main id="contenu-produit" className="product-main p-page mf-page">
      <VitrineStudio titre="Fichiers" description="Tous tes projets et tes sessions se retrouvent dans une même mémoire."
        libelleApercus="Fichiers récents"
        apercus={recents.map((item) => ({
          id: item.id, titre: item.titre, detail: LIBELLE_TYPE[item.objet.type], visuel: <Miniature entite={item} taille={42} />,
          ouvrir: () => ouvrirApercu(item.id),
        }))}
        actions={
          <div className="mf-entete-actions">
            {!source.demo && espaces.length > 1 && <label className="mf-espace"><Folder size={16} aria-hidden />
              <select className="champ" aria-label="Projet d’importation" value={source.espace} onChange={(e) => changerEspace(e.target.value)}>
                {Array.from(new Set([source.espace, ...espaces.map((x) => x.nom)])).map((nom) => <option key={nom} value={nom}>{nom === "accueil" ? "Accueil" : nom}</option>)}
              </select></label>}
            {!journalActif && <><input ref={fichier} type="file" hidden onChange={(e) => void importer(e)} accept="image/*,video/*,audio/*,.pdf,.md,.txt,.csv,.json,.srt,.vtt" />
            <button type="button" className="p-button p-primary" disabled={envoi} onClick={() => fichier.current?.click()}>
              <Plus size={17} />{envoi ? "Importation…" : "Importer un fichier"}</button></>}
          </div>
        } />
      <div className="mf-perimetre mf-perimetre-global"><Folder size={13} aria-hidden /><label>
        <span className="sr-only">Projet du graphe</span><select className="champ" aria-label="Projet du graphe" value={projet}
          onChange={(e) => { setProjet(e.target.value); filtrer(); }}><option value="">Tous les projets</option>
          {global.projets.map((p) => <option key={p.nom} value={p.nom}>{p.nom === "accueil" ? "Accueil" : p.nom}</option>)}
        </select></label><span>{global.couverture.sessions.charges}/{global.couverture.sessions.total} sessions · Références de la bibliothèque</span></div>
      <div className="mf-barre">
        <div className="mf-segment" role="group" aria-label="Affichage des fichiers">
          <button type="button" aria-pressed={graphe && !journalActif} onClick={() => changerMode("graphe")}><Workflow size={16} />Graphe de mémoire</button>
          <button type="button" aria-pressed={!graphe} onClick={() => changerMode("liste")}><List size={16} />Liste</button>
          <button type="button" aria-pressed={journalActif} onClick={() => changerMode("journal")}><History size={16} />Journal</button>
        </div>
        {graphe && <div className="mf-segment" role="group" aria-label="Disposition du graphe">
          <button type="button" aria-pressed={disposition === "constellation"} onClick={() => changerGraphe("constellation")}><Radio size={15} />Constellation</button>
          <button type="button" aria-pressed={disposition === "flux"} onClick={() => changerGraphe("flux")}><Router size={15} />Par niveaux</button>
        </div>}
        {journalActif ? <CommandesJournal journal={journal} demo={source.demo} filtrer={(nature) => { setFocus(null); journal.filtrer(nature); }} /> : <label className="mf-type"><span className="sr-only">Type de fichier</span><select className="champ" value={type}
          onChange={(e) => { setType(e.target.value); filtrer(); }}><option value="">Tous les points</option>
          {TYPES.map((t) => <option key={t} value={t}>{LIBELLE_TYPE[t]}</option>)}
          {graphe && <><option value="reference">Références</option><option value="observation">Observations</option><option value="memoire">Événements des agents</option>
            <option value="mission">Missions</option><option value="dossier">Dossiers</option></>}</select></label>}
        {!journalActif && <span className="mf-compte tab-num" role="status">{modele ? `${compte}${graphe ? ` · ${references.references.length}/${references.total} références` : ""}` : "Chargement…"}</span>}
      </div>
      {global.erreur && <div className="p-error" role="alert">{global.erreur}<button className="p-button p-quiet" onClick={global.actualiser}><RefreshCw size={15} />Actualiser les projets et sessions</button></div>}
      {global.avertissements.length > 0 && <details className="mf-limites-globales"><summary>Sources disponibles</summary>
        <ul>{global.avertissements.map((texte) => <li key={texte}>{texte}</li>)}</ul></details>}
      {references.erreur && <div className="p-error" role="alert">{references.erreur}<button className="p-button p-quiet" onClick={references.actualiser}><RefreshCw size={15} />Actualiser les sources</button></div>}
      {!journalActif && journal.erreur && <div className="p-error" role="alert">{journal.erreur}<button className="p-button p-quiet" onClick={journal.reessayer}><RefreshCw size={15} />Actualiser le journal</button></div>}
      {erreur && <div className="p-error" role="alert">{erreur}<button className="p-button p-quiet" onClick={() => void charger()}><RefreshCw size={15} />Actualiser</button></div>}
      {modele && projection && <div className="mf-poste">
        <section ref={scene} className="mf-scene" aria-label={graphe ? "Graphe de mémoire" : "Inventaire des fichiers"}>
          {focus && graphe && <div className="mf-focus">
            <button type="button" className="p-button p-quiet" onClick={() => setFocus(null)}><X size={15} />Quitter le voisinage</button>
            <label>Distance <select className="champ" value={profondeur} onChange={(e) => setProfondeur(Number(e.target.value))}>
              <option value={1}>1 lien</option><option value={2}>2 liens</option><option value={3}>3 liens</option></select></label>
          </div>}
          {graphe && !graphePrepare && <p className="mf-assemblage" role="status">Assemblage de la mémoire…</p>}
          {graphe && graphePrepare && (projection.ids.length > 0 || !!modeleAffiche?.groupes?.length) && <CarteGraphe
            key={`${disposition}:${focus ?? ""}`} modele={modeleAffiche!} projection={projection} disposition={disposition} centre={focus}
            groupesParDefaut nomAccessible="Graphe de mémoire" choisirGroupe={choisirSession} effacerSelection={effacerSelection}
            cleDisposition={global.cle_disposition + (source.demo ? ":demo" : ":reel")}
            selection={groupeActif ? "centroide:" + groupeActif.id : demande ? selection?.id ?? null : null} liensContexte={contexte.liens} choisir={choisir} onInit={(rf) => { centrer.current = (id) => {
              const n = rf.getNode(id);
              if (n) void rf.setCenter(n.position.x + 76, n.position.y + 26, { zoom: Math.max(.92, rf.getZoom()), duration: 0 });
            }; }} />}
          {journalActif && <ListeJournal journal={journal} entrees={entreesJournal} demo={source.demo} recherche={rechercheJournal}
            selection={selection?.id} choisir={ouvrirApercu} />}
          {graphe && <p className="mf-geste">Déplace un centroïde pour déplacer son groupe. Place chaque point librement. Les noms apparaissent au clic ou à fort zoom.</p>}
          {graphe && <div className="mf-couverture" role="status"><span>{projection.ids.length} points affichés · {modele.entites.size} chargés</span>
            {ignorer && <span>Affine la recherche pour retrouver un autre point.</span>}
            {(references.charge || global.charge) && <span>Chargement de la mémoire…</span>}
            {global.suivant && <button type="button" className="p-button p-quiet" disabled={global.charge} onClick={global.suivant}>Charger d’autres projets et sessions <ArrowRight size={15} /></button>}
            {references.suivant && <button type="button" className="p-button p-quiet" disabled={references.charge} onClick={references.suivant}>Charger d’autres références <ArrowRight size={15} /></button>}
          </div>}
          {!graphe && fichiers.length > 0 && <div className="mf-liste">
            <ul>{fichiers.slice((pageActive - 1) * TAILLE_PAGE, pageActive * TAILLE_PAGE).map((x) => <li key={x.id}>
              <SpotlightCard as="button" type="button" className="mf-ligne" aria-pressed={x.id === selection?.id} onClick={() => choisir(x.id)}>
                <span className="mf-miniature"><Miniature entite={x} /></span><span><strong>{x.titre}</strong><small>{x.objet?.asset?.nom || LIBELLE_TYPE[x.type]}</small></span>
                <span className="mf-ligne-liens">{modele.adjacents.get(x.id)?.length ?? 0} lien(s)</span>
                <span className="tab-num">{x.objet ? dateCourte(x.objet.maj) : ""}</span>
              </SpotlightCard>
            </li>)}</ul>
            {totalPages > 1 && <nav className="mf-pagination" aria-label="Pagination des fichiers">
              <button className="p-icon-button" type="button" aria-label="Page précédente" disabled={pageActive <= 1} onClick={() => setPage(pageActive - 1)}><ChevronLeft size={17} /></button>
              {pageActive} / {totalPages}
              <button className="p-icon-button" type="button" aria-label="Page suivante" disabled={pageActive >= totalPages} onClick={() => setPage(pageActive + 1)}><ChevronRight size={17} /></button>
            </nav>}
          </div>}
          {!journalActif && (graphe ? projection.ids.length === 0 && !modeleAffiche?.groupes?.length : fichiers.length === 0) && !focus && <div className="mf-vide"><FileText size={29} />
            <h2>{racines.length || modele.entites.size ? "Aucun élément correspondant" : "Ta mémoire est prête à accueillir ses premiers éléments"}</h2>
            <p>{modele.entites.size ? "Essaie une autre recherche ou un autre format." : "Importe un fichier ou ajoute une référence pour commencer."}</p>
          </div>}
          {graphe && projection.ids.length > 0 && <div className="mf-legende is-types" aria-label="Relations du graphe">
            <span data-relation="inspire">Inspiration</span><span data-relation="alimente">Alimentation</span>
            <span data-relation="depend">Dépendance</span><span data-relation="source">Référence</span>
            {projection.relations.some((r) => r.style === "wikilien") && <span data-relation="wikilien">Wikilien</span>}
            {projection.relations.some((r) => r.style === "memoire") && <span data-relation="memoire">Preuve de mission</span>}
            {projection.relations.some((r) => r.style === "causalite") && <span data-relation="causalite">Événement lié</span>}
            {contexte.liens.size > 0 && <span data-relation="contexte">Source de contexte</span>}
          </div>}
        </section>
        {sessionActive && <InspecteurSession session={sessionActive} modele={modele} choisir={ouvrirApercu} />}
        {groupeActif && !sessionActive && <InspecteurGroupe groupe={groupeActif} modele={modele} choisir={ouvrirApercu} />}
        {selection?.reference ? <InspecteurReferences key={selection.reference} refInspecteur={inspecteur}
          referenceId={selection.reference} reference={selection.sourceRag} fiche={references.referenceChargee?.id === selection.reference ? references.referenceChargee : undefined}
          observation={selection.observation} charge={references.chargeReference} erreur={references.erreur}
          choisir={ouvrirApercu} ouvrir={(observation) => aller("references", { ref: selection.reference!, ...(observation ? { observation } : {}) })}
          reessayer={() => void references.chargerReference(selection.reference!)} /> : selection && <Inspecteur key={selection.id} refInspecteur={inspecteur} entite={selection} modele={modele} source={sourceSelection} lecture={contexte.lecture}
          choisir={(id) => modele.entites.has(id) ? ouvrirApercu(id) : aller("board", { carte: id })} isoler={() => { changerAffichage(dernierGraphe.current); setFocus(selection.id); }}
          ouvrirBoard={() => aller("board", { carte: selection.id, ...(selection.objet?.espace ? { espace: selection.objet.espace } : {}) })} ouvrirMission={(mission) => aller("missions", { mission, ...(selection.projet ? { espace: selection.projet } : {}) })} ouvrirReference={ouvrirReference} ouvrirSources={ouvrirSources}
          relier={() => setRelier(true)} actualiser={charger} signaler={setNotice} />}
      </div>}
      {relier && selection?.objet && board && <LienFichiers source={sourceSelection} origine={selection.objet} objets={global.objets.filter((o) => o.espace === selection.objet!.espace)}
        fermer={() => setRelier(false)} cree={() => { setRelier(false); setNotice("Relation ajoutée sur le Board."); void charger(); }} />}
      {notice && <div className="p-feedback" role="status">{notice}</div>}
    </main>
  </div>;
}

function InspecteurGroupe({ groupe, modele, choisir }: { groupe: GroupeGraphe; modele: Graphe; choisir: (id: string) => void }) {
  return <aside className="mf-inspecteur mf-session" aria-label="Inspecteur du groupe">
    <header className="mf-inspect-entete"><span className="mf-miniature"><Folder size={20} /></span>
      <div><p>Éléments du projet</p><h2>{groupe.projet || groupe.titre}</h2></div></header>
    <p className="mf-description">Leur session d’origine est inconnue dans les données enregistrées.</p>
    <ul className="mf-session-membres">{groupe.ids.map((id) => {
      const e = modele.entites.get(id);
      return e && <li key={id}><button type="button" onClick={() => choisir(id)}><Miniature entite={e} /><span>{e.titre}</span></button></li>;
    })}</ul>
  </aside>;
}

function InspecteurSession({ session, modele, choisir }: { session: SessionGraphe; modele: Graphe; choisir: (id: string) => void }) {
  const membres = [...modele.entites.values()].filter((e) => e.sessionId === session.id || e.sessionIds?.includes(session.id));
  const origines = { tentative: "Session d’exécution", runtime: "Session d’agent", workmux: "Lancement enregistré" };
  const etats: Record<string, string> = { running: "En cours", en_cours: "En cours", working: "En cours", succeeded: "Réussie",
    SUCCEEDED: "Réussie", failed: "Échouée", FAILED: "Échouée", cancelled: "Annulée", planned: "Préparée",
    waiting: "En attente", attente: "En attente", terminee: "Terminée", done: "Terminée", lancee: "Lancée",
    blocked: "Bloquée", paused: "En pause", awaiting_review: "À relire", lost: "Interrompue", perdue: "Interrompue" };
  return <aside className="mf-inspecteur mf-session" aria-label="Inspecteur de la session">
    <header className="mf-inspect-entete"><span className="mf-miniature"><Workflow size={20} /></span>
      <div><p>{origines[session.origine]}</p><h2>{session.titre}</h2></div></header>
    <p className="mf-description">{session.projets.join(" · ") || "Projet non renseigné"}</p>
    <dl className="mf-session-infos"><div><dt>État enregistré</dt><dd>{etats[session.statut] ?? session.statut}</dd></div>
      {session.debut !== null && <div><dt>Début</dt><dd>{dateHeure(session.debut)}</dd></div>}
      {session.fin !== null && <div><dt>Fin</dt><dd>{dateHeure(session.fin)}</dd></div>}
      <div><dt>Identifiant</dt><dd><code>{session.id}</code></dd></div></dl>
    <h3>Éléments rattachés</h3>
    {membres.length ? <ul className="mf-session-membres">{membres.map((e) => <li key={e.id}>
      <button type="button" onClick={() => choisir(e.id)}><Miniature entite={e} /><span>{e.titre}</span>
        {e.sessionIds && e.sessionIds.length > 1 && <small>Partagé</small>}</button>
    </li>)}</ul> : <p className="mf-description">Aucun élément rattaché dans les données chargées.</p>}
  </aside>;
}

function Inspecteur({ refInspecteur, entite, modele, source, lecture, choisir, isoler, ouvrirBoard, ouvrirMission, ouvrirReference, ouvrirSources, relier, actualiser, signaler }: {
  refInspecteur: Ref<HTMLElement>; entite: Entite; modele: Graphe; source: Source; choisir: (id: string) => void; isoler: () => void; ouvrirBoard: () => void;
  lecture: ReturnType<typeof useContexteCarte>["lecture"]; ouvrirMission: (id: string) => void;
  ouvrirReference: (ref: string, fragment?: string) => void; ouvrirSources: (ref?: string) => void; relier: () => void; actualiser: () => Promise<void>; signaler: (t: string) => void;
}) {
  const o = entite.objet;
  const fichier = o && estFichier(o);
  const relations = modele.adjacents.get(entite.id) ?? [];
  const wikiliens = relations.filter((r) => r.style === "wikilien");
  const groupes = regrouperRelations(relations.filter((r) => r.style !== "wikilien")).sort((a, b) => Number(b.cible === entite.id) - Number(a.cible === entite.id));
  const [max, setMax] = useState(12);
  const a = o?.asset;
  const [edition, setEdition] = useState<{ contenu: string; version: number } | null>(null);
  const [enregistrement, setEnregistrement] = useState(false);
  const [erreurNote, setErreurNote] = useState("");
  const note = o && estNote(o) ? o : null;
  const quitterEdition = () => { setEdition(null); setErreurNote(""); };
  const enregistrerNote = async () => {
    if (!edition || !note || enregistrement) return;
    setEnregistrement(true); setErreurNote("");
    try {
      const [resultat] = await source.modifier([{ id: note.id, version: edition.version, champs: { contenu: edition.contenu } }]);
      if (!resultat?.ok) {
        if (resultat?.code === "conflit") {
          await actualiser();
          throw new Error("La note a changé. Copie ton brouillon si nécessaire, puis rouvre la note.");
        }
        throw new Error(resultat?.erreur || "Enregistrement impossible.");
      }
      await actualiser();
      quitterEdition();
      signaler("Note enregistrée.");
    } catch (e) { setErreurNote(message(e)); }
    finally { setEnregistrement(false); }
  };
  const notes = modele.notes.notes;
  return <aside ref={refInspecteur} tabIndex={-1} className="mf-inspecteur" aria-label={entite.memoire ? "Inspecteur de l’événement" : "Inspecteur du fichier"}>
    <header className="mf-inspect-entete"><span className="mf-miniature"><Miniature entite={entite} /></span>
      <div><p>{entite.memoire ? NATURES_MEMOIRE[entite.memoire.nature] : entite.reference ? "Référence" : LIBELLE_TYPE[entite.type] ?? entite.type}</p><h2>{entite.titre}</h2></div></header>
    {o?.meta.description && <p className="mf-description">{o.meta.description}</p>}
    {a && <p className="mf-metadata tab-num">{[taille(a.taille), a.meta.duree ? duree(a.meta.duree) : "",
      a.meta.largeur && a.meta.hauteur ? `${a.meta.largeur} × ${a.meta.hauteur}` : a.mime].filter(Boolean).join(" · ")}</p>}
    <div className="mf-inspect-actions">
      {entite.missionId && <button type="button" className="p-button p-quiet" onClick={() => ouvrirMission(entite.missionId!)}><ArrowUpRight size={15} />Ouvrir la mission</button>}
      {o && <button type="button" className="p-button p-quiet" onClick={ouvrirBoard}><LayoutGrid size={15} />Voir sur le Board</button>}
      {entite.reference && <button type="button" className="p-button p-quiet" onClick={() => ouvrirReference(entite.reference!)}><Database size={15} />Voir la référence</button>}
      {(entite.reference || o?.meta.reference_id) && <button type="button" className="p-button p-quiet"
        onClick={() => ouvrirSources(entite.reference || o?.meta.reference_id)}><Workflow size={15} />Explorer les observations</button>}
      {a?.url && <a className="p-button p-quiet" href={a.url} target="_blank" rel="noopener noreferrer">Original <ArrowUpRight size={15} /></a>}
    </div>
    {entite.memoire && <FicheEntreeJournal entree={entite.memoire} demo={source.demo} />}
    <ContexteCarte lecture={lecture} demo={source.demo} choisir={choisir} ouvrirReference={ouvrirReference} actualiser={actualiser} />
    {fichier && !edition && <ApercuFichier objet={o} titre={entite.titre}
      wiki={note ? { resoudre: (cible) => resoudreWiki(modele.notes, note, cible), ouvrir: choisir } : undefined}
      editer={note ? () => setEdition({ contenu: note.contenu, version: note.version }) : undefined} />}
    {note && edition && <form className="mf-edition-note" onSubmit={(e) => { e.preventDefault(); void enregistrerNote(); }}>
      <h3>Modifier la note</h3>
      <EditeurNote valeur={edition.contenu} surChangement={(contenu) => setEdition((brouillon) => brouillon && { ...brouillon, contenu })}
        cibles={(requete) => ciblesWiki(notes, note, requete)} surEchapper={() => { if (!enregistrement) quitterEdition(); }} />
      {erreurNote && <p className="p-error" role="alert">{erreurNote}</p>}
      <div className="mf-inspect-actions">
        <button type="submit" className="p-button p-primary" disabled={enregistrement || edition.contenu === note.contenu}>
          {enregistrement ? "Enregistrement…" : "Enregistrer la note"}</button>
        <button type="button" className="p-button p-quiet" disabled={enregistrement} onClick={quitterEdition}>Annuler</button>
      </div>
    </form>}
    {note && wikiliens.length > 0 && <section className="mf-wikiliens mf-connexions" aria-label="Wikiliens de la note">
      {[{ entrants: true, titre: "Liens retour" }, { entrants: false, titre: "Liens sortants" }].map(({ entrants, titre }) => {
        const liens = wikiliens.filter((r) => (r.cible === entite.id) === entrants);
        if (!liens.length) return null;
        return <div key={titre}><div className="mf-partie-entete"><h3><Link2 size={16} />{titre} <span>{liens.length}</span></h3></div>
          <ul>{liens.map((r) => {
            const dest = modele.entites.get(autre(r, entite.id));
            if (!dest) return null;
            const Fleche = entrants ? ArrowDownLeft : ArrowUpRight;
            return <li key={r.id}><button type="button" onClick={() => choisir(dest.id)}>
              <span className="mf-miniature"><Miniature entite={dest} taille={15} /></span>
              <strong>{dest.titre}</strong><Fleche size={15} aria-hidden />
            </button></li>;
          })}</ul></div>;
      })}
    </section>}
    <section className="mf-connexions">
      <div className="mf-partie-entete"><h3><Link2 size={16} />Relations <span className="tab-num">{relations.length}</span></h3>
        {fichier && <button type="button" className="p-button p-quiet" onClick={relier}><Plus size={15} />Relier</button>}</div>
      {relations.length > 0 && <button type="button" className="p-button p-quiet mf-voisinage" onClick={isoler}><Workflow size={15} />Isoler le voisinage</button>}
      {groupes.length ? <>
        <ul>{groupes.slice(0, max).map((r) => {
          const dest = modele.entites.get(autre(r, entite.id));
          if (!dest) return null;
          const Fleche = r.source === entite.id ? ArrowUpRight : ArrowDownLeft;
          return <li key={r.id}><button type="button" onClick={() => choisir(dest.id)}>
            <span className="mf-miniature"><Miniature entite={dest} taille={15} /></span>
            <span><strong>{dest.titre}</strong><small>{r.cible === entite.id ? "Entrant" : "Sortant"} · {r.texte}{r.occurrences ? ` ×${r.occurrences}` : ""}</small></span><Fleche size={15} aria-hidden />
          </button></li>;
        })}</ul>
        {groupes.length > max && <button type="button" className="p-button p-quiet" onClick={() => setMax(max + 12)}>Afficher plus de relations</button>}
      </> : <p className="mf-apercu-message">Aucun lien sur le Board.</p>}
    </section>
    {fichier && !estNote(o) && <MemoireFichier entite={entite} demo={source.demo} indexee={actualiser} ouvrir={ouvrirReference} signaler={signaler} />}
  </aside>;
}

function LienFichiers({ source, origine, objets, fermer, cree }: {
  source: Source; origine: ObjetBoard; objets: ObjetBoard[]; fermer: () => void; cree: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titre = useId();
  const [q, setQ] = useState("");
  const [destination, setDestination] = useState("");
  const [style, setStyle] = useState<StyleLien>("inspire");
  const [label, setLabel] = useState("");
  const [erreur, setErreur] = useState("");
  const [occupe, setOccupe] = useState(false);
  useLayoutEffect(() => {
    const d = ref.current;
    d?.showModal();
    return () => { d?.close(); };
  }, []);
  const choix = useMemo(() => objets.filter((o) => o.id !== origine.id && !["trait", "fleche", "forme"].includes(o.type) &&
    (!q || mot(titreDe(o)).includes(mot(q.trim())))).slice(0, 100), [objets, origine, q]);
  return <dialog className="mf-relation-dialogue" ref={ref} aria-labelledby={titre} onCancel={(e) => { e.preventDefault(); if (!occupe) fermer(); }}>
    <form onSubmit={async (e) => {
      e.preventDefault();
      if (!destination || occupe) return;
      setOccupe(true); setErreur("");
      try { await source.lier(origine.id, destination, label.trim(), style); cree(); }
      catch (e) { setErreur(message(e)); setOccupe(false); }
    }}>
      <header><h2 id={titre}>{estNote(origine) ? "Relier une note" : "Relier un fichier"}</h2><button type="button" className="p-icon-button" aria-label="Fermer" disabled={occupe} onClick={fermer}><X size={17} /></button></header>
      <p>Depuis <strong>{titreDe(origine)}</strong></p>
      <label><span>Rechercher la carte cible</span><input className="champ" type="search" value={q} onChange={(e) => { setQ(e.target.value); setDestination(""); }} /></label>
      <label><span>Carte cible</span><select className="champ" value={destination} onChange={(e) => setDestination(e.target.value)}>
        <option value="">{choix.length ? "Choisir une carte" : "Aucune carte trouvée"}</option>
        {choix.map((o) => <option key={o.id} value={o.id}>{titreDe(o)} · {LIBELLE_TYPE[o.type] ?? o.type}</option>)}</select></label>
      <label><span>Relation</span><select className="champ" value={style} onChange={(e) => setStyle(e.target.value as StyleLien)}>
        {TYPE_LIENS.map((r) => <option key={r} value={r}>{LIBELLES[r]}</option>)}</select></label>
      <label><span>Libellé (facultatif)</span><input className="champ" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={120} /></label>
      {erreur && <p className="p-error" role="alert">{erreur}</p>}
      <button type="submit" className="p-button p-primary" disabled={!destination || occupe}><Link2 size={16} />Enregistrer la relation</button>
    </form>
  </dialog>;
}
