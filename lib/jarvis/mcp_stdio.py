"""Transport MCP stdio local, configuré par le propriétaire et sans interpréteur de commandes.

Chaque découverte ou appel possède son processus et son délai total. Le contrôle de connexion et du
mandat est fourni par l'appelant ; aucune réponse du serveur ne peut élargir cette autorisation. Le
processus local garde les droits de l'utilisateur Linux : ce transport n'est pas un bac à sable.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import selectors
import signal
import subprocess
import time
from pathlib import Path

from . import annulation as arret

_ENV = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,99}\Z")
_OUTIL = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}\Z")
_PROTOCOLES = {"2025-03-26", "2025-06-18", "2025-11-25"}
_MAX_MESSAGE = 1_000_000
_MAX_SESSION = 8_000_000
_MAX_ENTREE = 128_000
_MAX_STDERR = 64_000


class StdioError(ValueError):
    """Erreur publique sans argv, stderr, contenu du fournisseur ou valeur d'environnement."""


def valider_configuration(spec: dict, *, verifier_fichiers: bool = True) -> dict:
    """Valide uniquement les champs de transport ; le contrôleur conserve identité et sélection."""
    if type(verifier_fichiers) is not bool:
        raise StdioError("Option de validation du transport stdio invalide.")
    if not isinstance(spec, dict) or not {"command"} <= set(spec) <= {"command", "args", "env_allowlist", "cwd"}:
        raise StdioError("Transport stdio : command requis ; args, env_allowlist et cwd facultatifs.")
    command = spec["command"]
    if (not isinstance(command, str) or not command or len(command) > 4000
            or any(ord(c) < 32 for c in command) or not Path(command).is_absolute()):
        raise StdioError("Commande stdio : chemin absolu exécutable requis.")
    if verifier_fichiers and (not Path(command).is_file() or not os.access(command, os.X_OK)):
        raise StdioError("Commande stdio absente ou non exécutable.")
    args = spec.get("args", [])
    if (not isinstance(args, list) or len(args) > 64
            or any(not isinstance(a, str) or len(a) > 16_000 or "\0" in a for a in args)
            or sum(len(a.encode("utf-8")) for a in args) > 64_000):
        raise StdioError("Arguments stdio invalides ou trop volumineux.")
    noms = spec.get("env_allowlist", [])
    if (not isinstance(noms, list) or len(noms) > 64
            or any(not isinstance(n, str) or not _ENV.fullmatch(n) for n in noms)
            or len(noms) != len(set(noms))):
        raise StdioError("env_allowlist : noms de variables distincts requis, sans valeurs.")
    cwd = spec.get("cwd", "/")
    if (not isinstance(cwd, str) or not cwd or len(cwd) > 4000 or any(ord(c) < 32 for c in cwd)
            or not Path(cwd).is_absolute() or (verifier_fichiers and not Path(cwd).is_dir())):
        raise StdioError("cwd stdio : répertoire absolu existant requis.")
    return {"command": command, "args": args.copy(), "env_allowlist": sorted(noms), "cwd": cwd}


def metadata(spec: dict) -> dict:
    """Métadonnées affichables ; ni les arguments ni les valeurs d'environnement ne sortent."""
    config = valider_configuration(spec, verifier_fichiers=False)
    try:
        executable = Path(config["command"]).is_file() and os.access(config["command"], os.X_OK)
        repertoire = Path(config["cwd"]).is_dir()
    except OSError:
        executable, repertoire = False, False
    return {"transport": "stdio", "executable": Path(config["command"]).name,
            "disponible": executable and repertoire,
            "raison": "" if executable and repertoire else "Exécutable ou répertoire local indisponible.",
            "env": [{"nom": n, "presente": bool(os.environ.get(n))} for n in config["env_allowlist"]]}


def _masquer(valeur, secrets):
    if isinstance(valeur, str):
        for secret in secrets:
            valeur = valeur.replace(secret, "[SECRET]")
        return valeur
    if isinstance(valeur, dict):
        return {_masquer(str(k), secrets): _masquer(v, secrets) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_masquer(v, secrets) for v in valeur]
    if type(valeur) in (int, float) and str(valeur) in secrets:
        return "[SECRET]"
    return valeur


class Client:
    """Session synchrone à requête unique en vol, avec fermeture obligatoire par contexte ou fermer()."""

    def __init__(self, spec: dict, *, verifier=None, annulation=None, timeout: float = 20):
        self.config = valider_configuration(spec)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise StdioError("Délai total stdio attendu entre zéro exclu et trente secondes.")
        if annulation is not None and not isinstance(annulation, arret.ControleExecution):
            raise StdioError("Contrôle d'annulation local invalide.")
        if verifier is not None and not callable(verifier):
            raise StdioError("Contrôle de connexion invalide.")
        self.verifier, self.annulation, self.timeout = verifier, annulation, timeout
        self.proc = None
        self._selecteur = selectors.DefaultSelector()
        self._sortie = bytearray()
        self._stdout_ferme = False
        self._stdout_total = 0
        self._stderr_total = 0
        self._stderr_tronque = False
        self._initialise = False
        self._ferme = False
        self._numero = 0
        self._echeance = None
        self._secrets = []
        self.protocole = ""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fermer()

    def _controle(self):
        if self._ferme:
            raise StdioError("Session stdio fermée.")
        if self.annulation:
            self.annulation.verifier()
        if self.verifier:
            self.verifier()
        if self._echeance is not None and time.monotonic() >= self._echeance:
            raise StdioError("Délai total de session MCP stdio dépassé.")

    def _demarrer(self):
        self._controle()
        if self.proc is not None:
            return
        # Aucun HOME, token, proxy ou environnement de session n'est implicitement hérité.
        env = {"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONUNBUFFERED": "1"}
        for nom in self.config["env_allowlist"]:
            if nom in os.environ:
                env[nom] = os.environ[nom]
        self._secrets = sorted({env[n] for n in self.config["env_allowlist"] if env.get(n)}, key=len, reverse=True)
        self._echeance = time.monotonic() + self.timeout

        def lancer():
            return subprocess.Popen([self.config["command"], *self.config["args"]], cwd=self.config["cwd"],
                                    env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    bufsize=0, start_new_session=os.name == "posix")
        try:
            self.proc = self.annulation.demarrer(lancer) if self.annulation else lancer()
            for pipe, nom in ((self.proc.stdout, "stdout"), (self.proc.stderr, "stderr")):
                os.set_blocking(pipe.fileno(), False)
                self._selecteur.register(pipe, selectors.EVENT_READ, nom)
            os.set_blocking(self.proc.stdin.fileno(), False)
        except OSError as exc:
            self.fermer()
            raise StdioError("Impossible de démarrer le serveur MCP stdio.") from exc

    def _pomper(self, attente: float, *, conserver=True):
        """Draine les deux sorties sans lecteur parallèle, sans conserver le stderr."""
        try:
            prets = self._selecteur.select(max(0, attente))
        except OSError as exc:
            raise StdioError("Lecture du serveur MCP stdio impossible.") from exc
        for cle, _ in prets:
            try:
                bloc = os.read(cle.fileobj.fileno(), 65_536)
            except BlockingIOError:
                continue
            except OSError as exc:
                raise StdioError("Lecture du serveur MCP stdio impossible.") from exc
            if not bloc:
                self._selecteur.unregister(cle.fileobj)
                if cle.data == "stdout":
                    self._stdout_ferme = True
                continue
            if cle.data == "stderr":
                self._stderr_total = min(2**31 - 1, self._stderr_total + len(bloc))
                self._stderr_tronque = self._stderr_total > _MAX_STDERR
            elif conserver:
                self._stdout_total += len(bloc)
                if self._stdout_total > _MAX_SESSION:
                    raise StdioError("Sortie totale du serveur MCP stdio trop volumineuse.")
                self._sortie.extend(bloc)
                # Une lecture peut contenir plusieurs lignes ; chacune est bornée à son extraction.
                if b"\n" not in self._sortie and len(self._sortie) > _MAX_MESSAGE:
                    raise StdioError("Message MCP stdio trop volumineux.")

    def _envoyer(self, message):
        self._controle()
        try:
            encoded = json.dumps(message, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        except (TypeError, ValueError, RecursionError) as exc:
            raise StdioError("Requête MCP stdio non sérialisable.") from exc
        if len(encoded) > _MAX_ENTREE:
            raise StdioError("Requête MCP stdio trop volumineuse.")
        offset = 0
        while offset < len(encoded):
            self._controle()
            try:
                offset += os.write(self.proc.stdin.fileno(), encoded[offset:])
            except BlockingIOError:
                self._pomper(min(arret.POLL_S, max(0, self._echeance - time.monotonic())))
            except (BrokenPipeError, OSError) as exc:
                raise StdioError("Le serveur MCP stdio a fermé son entrée.") from exc

    def _lire(self):
        while True:
            self._controle()
            if b"\n" in self._sortie:
                ligne, _, reste = self._sortie.partition(b"\n")
                self._sortie = bytearray(reste)
                if not ligne or len(ligne) > _MAX_MESSAGE:
                    raise StdioError("Ligne MCP stdio vide ou trop volumineuse.")
                try:
                    message = json.loads(ligne.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise StdioError("Message JSON du serveur MCP stdio invalide.") from exc
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    raise StdioError("Enveloppe JSON-RPC stdio invalide.")
                return message
            if self._stdout_ferme:
                raise StdioError("Le serveur MCP stdio s'est arrêté sans réponse complète.")
            self._pomper(min(arret.POLL_S, max(0, self._echeance - time.monotonic())))

    def appel(self, methode: str, params=None):
        if methode not in {"initialize", "tools/list", "tools/call", "ping"}:
            raise StdioError("Méthode MCP stdio non prise en charge.")
        if methode != "initialize" and not self._initialise:
            raise StdioError("La session MCP stdio doit être initialisée.")
        if methode == "initialize" and self._initialise:
            raise StdioError("La session MCP stdio est déjà initialisée.")
        if params is not None and not isinstance(params, dict):
            raise StdioError("Paramètres JSON-RPC stdio : objet attendu.")
        if methode == "tools/call" and (not params or not isinstance(params.get("name"), str)
                                       or not _OUTIL.fullmatch(params["name"])
                                       or not isinstance(params.get("arguments"), dict)):
            raise StdioError("Appel d'outil MCP stdio invalide.")
        self._demarrer()
        self._numero += 1
        message = {"jsonrpc": "2.0", "id": self._numero, "method": methode}
        if params is not None:
            message["params"] = params
        self._envoyer(message)
        for _ in range(65):
            reponse = self._lire()
            if "method" in reponse:
                if not isinstance(reponse["method"], str) or not reponse["method"]:
                    raise StdioError("Notification MCP stdio invalide.")
                if "id" in reponse:
                    ident = reponse["id"]
                    if type(ident) not in (int, str) or (isinstance(ident, str) and len(ident) > 200):
                        raise StdioError("Identifiant de requête MCP stdio invalide.")
                    # Le ping ne fait aucun travail ; les capacités non annoncées restent refusées.
                    if reponse["method"] == "ping":
                        self._envoyer({"jsonrpc": "2.0", "id": ident, "result": {}})
                    else:
                        self._envoyer({"jsonrpc": "2.0", "id": ident,
                                       "error": {"code": -32601, "message": "Méthode client non prise en charge"}})
                continue
            if type(reponse.get("id")) is not int or reponse["id"] != self._numero:
                raise StdioError("Réponse MCP stdio non corrélée à la requête.")
            if "error" in reponse or "result" not in reponse:
                raise StdioError("Erreur du fournisseur MCP stdio ou réponse invalide.")
            return _masquer(reponse["result"], self._secrets)
        raise StdioError("Trop de notifications MCP stdio avant la réponse.")

    def initialiser(self):
        resultat = self.appel("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                               "clientInfo": {"name": "JarvisOS", "version": "1"}})
        if not isinstance(resultat, dict) or resultat.get("protocolVersion") not in _PROTOCOLES:
            raise StdioError("Version MCP stdio négociée non prise en charge.")
        self.protocole = resultat["protocolVersion"]
        self._envoyer({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialise = True

    def decouvrir(self) -> list[dict]:
        if not self._initialise:
            self.initialiser()
        outils, noms, curseurs, curseur = [], set(), set(), None
        for _ in range(10):
            resultat = self.appel("tools/list", {"cursor": curseur} if curseur else {})
            if not isinstance(resultat, dict) or not isinstance(resultat.get("tools"), list):
                raise StdioError("Catalogue MCP stdio invalide.")
            for outil in resultat["tools"]:
                if (not isinstance(outil, dict) or not isinstance(outil.get("name"), str)
                        or not _OUTIL.fullmatch(outil["name"]) or outil["name"] in noms
                        or not isinstance(outil.get("inputSchema"), dict)
                        or not isinstance(outil.get("description", ""), str)):
                    raise StdioError("Outil MCP stdio invalide ou dupliqué.")
                try:
                    taille = len(json.dumps(outil["inputSchema"], allow_nan=False).encode())
                except (ValueError, TypeError, RecursionError) as exc:
                    raise StdioError("Schéma d'outil MCP stdio invalide.") from exc
                if taille > 32_000 or len(outils) >= 128:
                    raise StdioError("Catalogue ou schéma MCP stdio trop volumineux.")
                noms.add(outil["name"])
                outils.append({"name": outil["name"], "description": outil.get("description", "")[:4000],
                               "inputSchema": copy.deepcopy(outil["inputSchema"])})
            curseur = resultat.get("nextCursor")
            if not curseur:
                return outils
            if not isinstance(curseur, str) or len(curseur) > 2000 or curseur in curseurs:
                raise StdioError("Pagination MCP stdio invalide ou cyclique.")
            curseurs.add(curseur)
        raise StdioError("Pagination MCP stdio trop longue.")

    def diagnostic(self) -> dict:
        return {"stderr_octets": self._stderr_total, "stderr_tronque": self._stderr_tronque,
                "stderr_conserve": False}

    def fermer(self):
        if self._ferme:
            return
        self._ferme = True
        if self.proc is not None:
            # Les helpers d'annulation ciblent tout le groupe POSIX, y compris après sortie du parent.
            arret._signaler(self.proc, signal.SIGTERM)
            fin = time.monotonic() + arret.GRACE_S
            try:
                while self.proc.poll() is None and time.monotonic() < fin:
                    self._pomper(min(0.05, max(0, fin - time.monotonic())), conserver=False)
            except (OSError, StdioError):
                pass
            finally:
                arret._signaler(self.proc, signal.SIGKILL)
                try:
                    self.proc.wait(timeout=arret.GRACE_S)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=arret.GRACE_S)
                for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                    if pipe:
                        pipe.close()
        self._selecteur.close()
        self._sortie.clear()
        self._secrets.clear()


def decouvrir(spec: dict, *, verifier=None, annulation=None, timeout: float = 20) -> list[dict]:
    with Client(spec, verifier=verifier, annulation=annulation, timeout=timeout) as client:
        return client.decouvrir()


def appeler(spec: dict, nom: str, arguments: dict, *, avant_effet=None, verifier=None,
            annulation=None, timeout: float = 20) -> dict:
    """Aucun retry interne ; une réponse perdue après tools/call doit rester inconnue à la passerelle."""
    with Client(spec, verifier=verifier, annulation=annulation, timeout=timeout) as client:
        client.initialiser()
        if avant_effet is not None:
            avant_effet()
        resultat = client.appel("tools/call", {"name": nom, "arguments": arguments})
        if not isinstance(resultat, dict) or not isinstance(resultat.get("content", []), list):
            raise StdioError("Résultat d'outil MCP stdio invalide.")
        return resultat
