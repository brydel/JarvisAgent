from pathlib import Path


def lire_document(base, nom):
    return (Path(base) / nom).read_text(encoding="utf-8")
