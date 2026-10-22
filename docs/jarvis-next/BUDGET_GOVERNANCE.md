# Gouvernance du budget

But : maximiser le travail utile par allocation de modèle disponible, pas le nombre d'agents.

## VERIFIED (M1)

- Budget d'**inférence payante** par tenant, **zéro par défaut** (`definir_budget_inference`).
- Contrôle **avant l'envoi** : le routeur refuse une connexion payante sans budget restant ; la tâche passe en
  WAITING_PROVIDER sans créer de tentative (test `test_payant_sans_budget_refuse_avant_envoi`).
- Mode abonnement : clés d'API retirées de l'environnement du CLI (pas de bascule silencieuse vers le payant).
- Un fournisseur épuisé n'est pas contourné : la tâche bascule vers l'autre fournisseur compatible, ou attend.

## CURRENT (réutilisé)

`budgets.py` (enveloppes monétaires par catégorie, non renseigné = 0, réserve pour incident), `usage.py` et
`fournisseurs.py` (quotas publiés, fraîcheur, « inconnu » ≠ illimité), `couts.py` (équivalent API, estimé).

## PROPOSED

- Décompte du consommé payant (`consomme_centimes`) à partir du coût réel rapporté par l'API ; aujourd'hui rien
  de payant n'est exécuté, donc rien n'est décompté — et une consommation inconnue sera affichée « inconnue »,
  jamais 0.
- Infrastructure et inférence suivies séparément (catégories distinctes de `budgets.py`).
- Disjoncteurs : taux d'échec par fournisseur, coupure automatique d'une connexion au-delà d'un seuil, levée
  manuelle seulement.
- Les mesures d'abonnement ne sont pas une facturation : affichées comme estimations datées.
