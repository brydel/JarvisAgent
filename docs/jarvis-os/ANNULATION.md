# Annulation et perte de bail — JOS-006

Le coureur transmet désormais un jeton local `ControleExecution` aux adaptateurs. Il confirme son bail avant
la préparation et interdit de lancer un nouvel outil quand le jeton est annulé. Un refus du plan de contrôle,
une erreur de battement, une pause locale ou `coureur/STOP` interrompent le travail. L'expiration connue du
bail est aussi suivie par une horloge monotone : un battement bloqué ne maintient pas l'autorité indéfiniment.
Une réponse de renouvellement arrivée après cette expiration ne réactive pas le jeton.

Le service peut aussi fournir son `threading.Event` d'arrêt avec `Coureur(..., stop=evenement)`. Ce signal
est consulté avant toute réclamation et pendant les opérations annulables. Le service doit poser ce signal,
joindre les voies du coureur jusqu'à la fin du nettoyage, puis seulement libérer son verrou d'identité et
son bail d'orchestrateur. Quitter brutalement le processus Python ne remplace pas cette séquence.

Claude et Codex utilisent un sous-processus avec un nouveau groupe POSIX. À l'annulation ou au dépassement
du délai, le groupe reçoit TERM, puis KILL ; les outils enfants du même groupe sont donc arrêtés aussi. Le
CLI ne garde pas d'outil en arrière-plan après sa fin. La lecture web préparatoire utilise le même mécanisme,
y compris pendant DNS ou TLS, avec une limite totale de 30 secondes ; les règles anti-SSRF restent celles
de `apercus.py`.

Les battements sont espacés d'au plus deux secondes. Les CLI vérifient le jeton toutes les 100 ms ; après
détection, leur nettoyage dispose de deux délais d'une seconde. La latence d'un transport de contrôle
reste distincte : s'il bloque, l'échéance locale du bail borne la continuation. Les processus qui quittent
volontairement leur groupe ne sont pas isolés par un groupe POSIX ; un bac à sable/cgroup est nécessaire
contre ce comportement.

Après annulation, aucun contenu tardif n'entre dans le journal des résultats à réémettre. Le résultat ne
part pas au plan de contrôle. Une course avec la toute dernière réponse reste couverte côté serveur par
le jeton de clôture historique : une tentative périmée ne peut pas créer un artefact accepté.

## Contrat pour un nouvel outil

```python
from jarvis.annulation import controle, executer_processus, verifier

verifier(enveloppe)
resultat = executer_processus(
    commande,
    timeout=30,
    annulation=controle(enveloppe),
)
verifier(enveloppe)
```

Le jeton est ajouté dans `enveloppe['_annulation']` par le coureur après validation de l'enveloppe reçue.
Il n'est ni sérialisé dans le protocole, ni transmis au modèle. Un adaptateur personnalisé doit appliquer
ce contrat avant de déclarer `capacites['annulation'] = True`. Un appel Python personnalisé qui ignore
le jeton n'est pas tué par magie ; son résultat reste refusé après annulation. La classe de base ne
déclare donc plus cette capacité par défaut.

Un effet externe déjà parti ne peut pas être annulé rétroactivement. Son rapprochement fournisseur et
son éventuel résultat inconnu relèvent du journal d'opérations JOS-007. Ce lot ne met pas en place de
bail sur les sessions de code workmux historiques.

## Vérification

```bash
python3 -m unittest discover -s tests -p 'test_annulation_execution.py' -v
```

Les tests lancent de vrais processus locaux et leurs enfants, dont certains ignorent TERM. Ils vérifient
le refus avant lancement, KILL après annulation et timeout, l'intégration des deux CLI, l'interruption de
la préparation web, l'annulation d'une mission et l'expiration pendant un battement bloqué. Aucun modèle,
serveur distant ou envoi réel n'est utilisé.
