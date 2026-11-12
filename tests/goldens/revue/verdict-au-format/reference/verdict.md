VERDICT : CORRECTIONS
Corrections exigées :
1. [bloquant] app/remise.py:6 — seul `pct < 0` est refusé : `remise(100, 150)` rend -50.0 ; lever ValueError au-dessus de 100 (critère 1)
2. [bloquant] app/remise.py:8 — aucun arrondi : `remise(19.99, 15)` rend 16.9915 ; arrondir au centime (critère 2)
3. [majeur] tests/test_remise.py:10 — aucun test du refus au-dessus de 100 ni de l'arrondi (critère 3)
Suggestions :
- aucune
Vérifications :
- `python3 -m unittest discover -s tests -t .` → OK, 2 tests : la suite passe parce qu'elle ne teste pas les critères 1 et 2
- `python3 -c "from app.remise import remise; print(remise(100, 150), remise(19.99, 15))"` → -50.0 16.9915
