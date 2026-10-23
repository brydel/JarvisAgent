# Prototype de workflows Temporal

Service Python séparé du cœur `lib/jarvis/`, avec SDK épinglé. Il exécute un DAG borné d'appels à la
passerelle Jarvis. Les phases `plan`, `recherche`, `production`, `revue` sont des étiquettes d'étape ;
ce service ne prétend pas qu'un modèle sait déjà construire ce plan ou réaliser chaque phase.

Voir [le périmètre et les preuves](../../docs/jarvis-os/TEMPORAL.md).

```bash
python3 -m venv /workspace/.jarvis-cloud/temporal-venv
/workspace/.jarvis-cloud/temporal-venv/bin/python -m pip install -r services/workflows_temporal/requirements.txt
export PYTHONPATH="$PWD/services/workflows_temporal"
/workspace/.jarvis-cloud/temporal-venv/bin/python -m jarvis_temporal valider services/workflows_temporal/exemples/projet.json
/workspace/.jarvis-cloud/temporal-venv/bin/python -m unittest discover -s services/workflows_temporal/tests -v
```

Le cœur Jarvis reste utilisable sans ce venv et sans SDK Temporal. Ne pas placer de dépendance pip dans `lib/jarvis/`.
