"""Client HTTP local. Le secret est lu au moment de l'activité et ne passe jamais dans le workflow."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
from urllib.parse import urlsplit

MAX_REPONSE = 256_000


class ErreurControleur(Exception):
    def __init__(self, message: str, *, definitive: bool):
        super().__init__(message)
        self.definitive = definitive


class Controleur:
    def __init__(self, url: str, fichier_jeton: str, *, timeout: float = 15):
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise ValueError("Ce prototype accepte uniquement le Studio HTTP local, sans identifiants dans l'URL.")
        if not 1 <= timeout <= 30:
            raise ValueError("Délai HTTP entre 1 et 30 secondes attendu.")
        self.hote = parsed.hostname
        self.port = parsed.port or 80
        self.fichier_jeton = Path(fichier_jeton)
        self.timeout = timeout

    def _requete(self, route: str, corps: dict, *, cookie: str = "") -> tuple[dict, str]:
        connexion = http.client.HTTPConnection(self.hote, self.port, timeout=self.timeout)
        entetes = {"Content-Type": "application/json", "X-Jarvis-Studio": "1"}
        if cookie:
            entetes["Cookie"] = cookie
        try:
            connexion.request("POST", route, json.dumps(corps, allow_nan=False).encode(), entetes)
            reponse = connexion.getresponse()
            contenu = reponse.read(MAX_REPONSE + 1)
            if len(contenu) > MAX_REPONSE:
                raise ErreurControleur("Réponse du contrôleur trop volumineuse.", definitive=True)
            if reponse.status != 200:
                raise ErreurControleur(f"Contrôleur HTTP {reponse.status}.",
                                       definitive=reponse.status not in {408, 429, 500, 502, 503, 504})
            try:
                valeur = json.loads(contenu)
            except (ValueError, UnicodeError) as exc:
                raise ErreurControleur("Réponse JSON du contrôleur invalide.", definitive=True) from exc
            if not isinstance(valeur, dict):
                raise ErreurControleur("Objet JSON du contrôleur attendu.", definitive=True)
            return valeur, (reponse.getheader("Set-Cookie") or "").split(";", 1)[0]
        except (OSError, http.client.HTTPException) as exc:
            # Ne pas propager URL, headers, corps ou valeurs de secrets dans l'historique d'erreur.
            raise ErreurControleur("Contrôleur local indisponible ; opération stable à rapprocher.", definitive=False) from exc
        finally:
            connexion.close()

    def executer(self, demande: dict, *, verifier_annulation=lambda: None) -> dict:
        verifier_annulation()
        try:
            if self.fichier_jeton.stat().st_size > 512:
                raise ValueError("taille")
            jeton = self.fichier_jeton.read_text().strip()
            if not 32 <= len(jeton) <= 512:
                raise ValueError("taille")
        except (OSError, ValueError, UnicodeError) as exc:
            raise ErreurControleur("Fichier de jeton Studio absent ou invalide.", definitive=True) from exc
        session, cookie = self._requete("/api/session", {"jeton": jeton})
        if not session.get("authentifie") or not cookie.startswith("jarvis_studio="):
            raise ErreurControleur("Session du Studio non établie.", definitive=True)
        verifier_annulation()
        resultat, _ = self._requete("/api/v2/outils/executer", demande, cookie=cookie)
        if resultat.get("operation_id") != demande["operation_id"]:
            raise ErreurControleur("Identité d'opération incohérente.", definitive=True)
        return resultat
