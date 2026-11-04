"""
Récupération de sorties disparues de la base TrailMaster.

Réinsère dans la base les sorties (randonnée, VTT, vélo, yoga...)
contenues dans data/sorties_perdues.json.gz, sans toucher à ce qui existe
déjà : une sortie déjà présente (même empreinte, ou même jour et même
distance) est ignorée. Une copie de la base est faite avant toute
modification, et le logiciel doit être fermé pendant l'opération.

Lancement : double-clic sur Recuperer_sorties.command
"""

import gzip
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DOSSIER = Path(__file__).parent
FICHIER = DOSSIER / "sorties_perdues.json.gz"


def _bases_candidates():
    """Emplacements possibles de la base (à côté du code, ou dossier
    permanent de l'application empaquetée)."""
    candidats = []
    try:
        sys.path.insert(0, str(DOSSIER.parent))
        from data import database as bdd
        candidats.append(Path(bdd.CHEMIN_BDD))
        try:
            candidats.append(Path(bdd._dossier_configuration_locale()) / "trailmaster.db")
        except Exception:
            pass
    except Exception:
        pass
    candidats.append(DOSSIER / "trailmaster.db")
    uniques = []
    for c in candidats:
        if c.exists() and c not in uniques:
            uniques.append(c)
    return uniques


def _choisir_base(chemin_force=None):
    if chemin_force:
        return Path(chemin_force)
    bases = _bases_candidates()
    if not bases:
        return None
    return max(bases, key=lambda c: c.stat().st_mtime)


def restaurer(chemin_base=None):
    base = _choisir_base(chemin_base)
    if base is None or not base.exists():
        print("Base TrailMaster introuvable. Lance d'abord TrailMaster une fois, puis ferme-le.")
        return 1

    with gzip.open(FICHIER, "rt", encoding="utf-8") as f:
        contenu = json.load(f)
    colonnes, lignes = contenu["colonnes"], contenu["lignes"]

    print(f"Base utilisée : {base}")
    copie = base.with_name(
        f"{base.name}.backup_avant_recuperation_{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(base, copie)
    print(f"Copie de sécurité : {copie.name}")

    conn = sqlite3.connect(base)
    cur = conn.cursor()
    existantes = {r[0] for r in cur.execute(
        "SELECT empreinte FROM activites WHERE empreinte IS NOT NULL")}
    par_jour = {}
    for jour, dist in cur.execute("SELECT substr(date,1,10), COALESCE(distance,0) FROM activites"):
        par_jour.setdefault(jour, []).append(dist)

    i_id = colonnes.index("id")
    i_emp = colonnes.index("empreinte")
    i_date = colonnes.index("date")
    i_dist = colonnes.index("distance")
    cols_ins = [c for c in colonnes if c != "id"]
    sql = f"INSERT INTO activites ({','.join(cols_ins)}) VALUES ({','.join('?' * len(cols_ins))})"

    ajoutees = ignorees = 0
    for l in lignes:
        dist = l[i_dist] or 0
        deja = (l[i_emp] and l[i_emp] in existantes) or any(
            abs(d - dist) <= max(0.3, 0.1 * dist) for d in par_jour.get(l[i_date][:10], []))
        if deja:
            ignorees += 1
            continue
        cur.execute(sql, [v for c, v in zip(colonnes, l) if c != "id"])
        ajoutees += 1
    conn.commit()
    conn.close()
    print(f"Sorties récupérées : {ajoutees} (déjà présentes, ignorées : {ignorees}).")
    print("Tu peux relancer TrailMaster.")
    return 0


if __name__ == "__main__":
    sys.exit(restaurer(sys.argv[1] if len(sys.argv) > 1 else None))
