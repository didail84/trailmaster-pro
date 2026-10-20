"""
Retrouver sa base TrailMaster quand les sorties « ont disparu ».

Cause la plus fréquente : le logiciel s'ouvre sur une base VIDE (ou plus
ancienne) parce que la nouvelle version a été dézippée dans un nouveau
dossier, ou parce que l'application empaquetée et le lancement par
« Lancer_TrailMaster.command » n'utilisent pas le même fichier.

Ce programme :
  1. cherche sur l'ordinateur tous les fichiers de base TrailMaster
     (trailmaster*.db, sauvegardes comprises) et affiche pour chacun la
     date, le nombre de sorties et la date de la dernière sortie ;
  2. indique quels fichiers le logiciel utilise réellement ;
  3. propose de remettre la base choisie (en général celle qui contient
     le plus de sorties) à la place de la base utilisée — après avoir
     mis de côté une copie de celle-ci. Rien n'est supprimé.

Lancement : double-clic sur Retrouver_ma_base.command
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DOSSIER = Path(__file__).parent
sys.path.insert(0, str(DOSSIER.parent))

DOSSIERS_IGNORES = {
    "node_modules", ".git", "Caches", "Cache", "Containers", "Photos Library.photoslibrary",
    "Applications", "Movies", "Music", "Pictures", ".Trash", "venv", ".venv", "site-packages",
}
PROFONDEUR_MAX = 5


def _chemins_logiciel():
    """(base utilisée en lancement normal, base de l'application empaquetée)"""
    normal = DOSSIER / "trailmaster.db"
    if sys.platform == "darwin":
        dossier = Path.home() / "Library" / "Application Support" / "TrailMaster Pro"
    elif sys.platform == "win32":
        dossier = Path(os.environ.get("APPDATA", Path.home())) / "TrailMaster Pro"
    else:
        dossier = Path.home() / ".local" / "share" / "TrailMaster Pro"
    empaquete = dossier / "trailmaster.db"

    synchro = None
    pointeur = dossier / "emplacement_synchronise.txt"
    if pointeur.exists():
        texte = pointeur.read_text(encoding="utf-8").strip()
        if texte:
            synchro = Path(texte) / "trailmaster.db"
    return normal, empaquete, synchro


def _chercher(racine):
    trouves = []
    racine = Path(racine)
    base_depth = len(racine.parts)
    for courant, dossiers, fichiers in os.walk(racine, onerror=lambda e: None):
        profondeur = len(Path(courant).parts) - base_depth
        dossiers[:] = [
            d for d in dossiers
            if d not in DOSSIERS_IGNORES and not (d == "Library" and profondeur == 0)
        ] if profondeur < PROFONDEUR_MAX else []
        for f in fichiers:
            bas = f.lower()
            if bas.startswith("trailmaster") and ".db" in bas and not bas.endswith(("-wal", "-shm", "-journal")):
                trouves.append(Path(courant) / f)
    return trouves


def _infos(chemin):
    try:
        conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
        cur = conn.cursor()
        nb, derniere = cur.execute("SELECT COUNT(*), MAX(date) FROM activites").fetchone()
        athletes = cur.execute("SELECT COUNT(*) FROM athletes").fetchone()[0]
        conn.close()
        return {"nb": nb or 0, "derniere": (derniere or "")[:10], "athletes": athletes}
    except Exception:
        return None


def main():
    normal, empaquete, synchro = _chemins_logiciel()
    print("Recherche des bases TrailMaster sur cet ordinateur (patience, ça peut durer une minute)...\n")

    candidats = {}
    racines = [Path.home() / d for d in ("Desktop", "Documents", "Downloads", "Bureau", "Téléchargements")]
    racines.append(Path.home() / "Library" / "Application Support" / "TrailMaster Pro")
    racines.append(DOSSIER.parent)
    racines.append(Path.home())
    for racine in racines:
        if racine.exists():
            for c in _chercher(racine):
                candidats[str(c.resolve())] = c.resolve()
    for p in (normal, empaquete, synchro):
        if p and p.exists():
            candidats[str(p.resolve())] = p.resolve()

    lignes = []
    for c in candidats.values():
        info = _infos(c)
        if info:
            lignes.append((c, info))
    if not lignes:
        print("Aucune base TrailMaster trouvée. Si tu as une sauvegarde ailleurs "
              "(clé USB, iCloud...), copie-la sur le Bureau et relance ce programme.")
        return 1

    lignes.sort(key=lambda x: (-x[1]["nb"], x[0].stat().st_mtime * -1))
    utilisees = {str(p.resolve()): nom for p, nom in
                 ((normal, "lancement normal (Lancer_TrailMaster)"),
                  (empaquete, "application empaquetée"),
                  (synchro, "dossier synchronisé")) if p and p.exists()}

    print(f"{'N°':<3} {'Sorties':>7}  {'Dernière sortie':<16} {'Modifié le':<17} Fichier")
    for i, (c, info) in enumerate(lignes, 1):
        modif = datetime.fromtimestamp(c.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        marque = f"   ← utilisé par : {utilisees[str(c)]}" if str(c) in utilisees else ""
        print(f"{i:<3} {info['nb']:>7}  {info['derniere'] or '—':<16} {modif:<17} {c}{marque}")

    print("\nBases que le logiciel ouvre :")
    print(f"  • lancement normal          : {normal}  ({'existe' if normal.exists() else 'ABSENTE'})")
    print(f"  • application empaquetée    : {empaquete}  ({'existe' if empaquete.exists() else 'ABSENTE'})")
    if synchro:
        print(f"  • dossier synchronisé actif : {synchro}")

    print("\nQuelle base veux-tu remettre en service ? (en général celle qui a le plus de sorties)")
    choix = input("Numéro (ou Entrée pour ne rien changer) : ").strip()
    if not choix.isdigit() or not 1 <= int(choix) <= len(lignes):
        print("Rien n'a été modifié.")
        return 0
    source = lignes[int(choix) - 1][0]

    cibles = [(p, nom) for p, nom in ((synchro, "dossier synchronisé"),
                                       (normal, "lancement normal"),
                                       (empaquete, "application empaquetée")) if p]
    if synchro:
        cibles = [cibles[0]]  # la synchro prime sur tout le reste
    print("\nOù la remettre ?")
    for i, (p, nom) in enumerate(cibles, 1):
        print(f"  {i}. {nom} : {p}")
    print(f"  {len(cibles) + 1}. toutes les cases ci-dessus")
    rep = input("Numéro : ").strip()
    if not rep.isdigit() or not 1 <= int(rep) <= len(cibles) + 1:
        print("Rien n'a été modifié.")
        return 0
    choisies = cibles if int(rep) == len(cibles) + 1 else [cibles[int(rep) - 1]]

    for p, nom in choisies:
        if p.resolve() == source:
            print(f"{nom} : c'est déjà cette base.")
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            copie = p.with_name(f"{p.name}.mis_de_cote_{datetime.now():%Y%m%d_%H%M%S}")
            shutil.copy2(p, copie)
            print(f"{nom} : ancienne base mise de côté ({copie.name})")
        shutil.copy2(source, p)
        os.chmod(p, 0o644)
        for suffixe in ("-wal", "-shm"):
            ancien = Path(str(p) + suffixe)
            if ancien.exists():
                ancien.unlink()
        print(f"{nom} : base remplacée par celle du fichier n°{choix}.")
    print("\nTerminé. Relance TrailMaster Pro.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
