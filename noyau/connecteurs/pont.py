"""
Le dossier partagé entre Claude et le logiciel (« pont »).

Chaque matin, la tâche programmée de Claude dépose dans un dossier Google Drive
« Trail Hub Center - Pont » un paquet trailhub-connecteurs-….json, et lit le
fichier trailhub-demandes.json écrit par le logiciel. Sur l'ordinateur, ce
dossier est le même grâce à Google Drive pour ordinateur (ou n'importe quel
dossier synchronisé) : il suffit de l'indiquer dans l'écran Connecteurs.

Sans dossier synchronisé, on peut aussi télécharger le paquet depuis Drive (ou
la page Claude) et l'importer à la main.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from data.database import obtenir_parametre, definir_parametre
from noyau.connecteurs import regles as R
from noyau.connecteurs import importer as I
from noyau.donnees import connecteurs as D

CLE_DOSSIER = "connecteurs_dossier"
CLE_ATHLETE = "connecteurs_athlete_id"
CLE_DERNIER_PASSAGE = "connecteurs_dernier_passage"
NOM_DOSSIER_DRIVE = "Trail Hub Center - Pont"


def dossier():
    d = obtenir_parametre(CLE_DOSSIER)
    return Path(d) if d else None


def definir_dossier(chemin):
    if chemin:
        p = Path(chemin)
        if not p.is_dir():
            raise R.ErreurConnecteurs(f"Le dossier « {chemin} » n'existe pas.")
        definir_parametre(CLE_DOSSIER, str(p))
    else:
        definir_parametre(CLE_DOSSIER, "")


def athlete_du_pont():
    v = obtenir_parametre(CLE_ATHLETE)
    try:
        return int(v) if v else None
    except ValueError:
        return None


def definir_athlete(athlete_id):
    definir_parametre(CLE_ATHLETE, str(athlete_id) if athlete_id else "")


def dossiers_probables():
    """Dossiers Google Drive habituels sur Mac, Windows et Linux (pour proposer un choix)."""
    maison = Path.home()
    candidats = [maison / "Google Drive" / "Mon Drive", maison / "Google Drive" / "My Drive", maison / "Google Drive",
                 maison / "Mon Drive", maison / "My Drive", Path("G:/Mon Drive"), Path("G:/My Drive")]
    cloud = maison / "Library" / "CloudStorage"
    if cloud.is_dir():
        for d in sorted(cloud.glob("GoogleDrive-*")):
            candidats += [d / "Mon Drive", d / "My Drive"]
    res = []
    for c in candidats:
        try:
            if c.is_dir():
                pont = c / NOM_DOSSIER_DRIVE
                res.append(pont if pont.is_dir() else c)
        except OSError:
            continue
    return res


def paquets_du_dossier(d=None):
    d = d or dossier()
    if not d or not d.is_dir():
        return []
    return sorted((p for p in d.iterdir() if p.is_file() and R.MOTIF_PAQUET.match(p.name)), key=lambda p: p.name)


def importer_fichier(chemin, athlete_id):
    try:
        texte = Path(chemin).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise R.ErreurConnecteurs(f"Lecture impossible de « {Path(chemin).name} » : {e}")
    return I.importer(texte, athlete_id, fichier=Path(chemin).name)


def ecrire_demandes(d=None):
    """Écrit trailhub-demandes.json avec les demandes en attente ; marque « envoyée » celles qui sont parties.
    Retourne le nombre de demandes écrites (None si pas de dossier)."""
    d = d or dossier()
    if not d or not d.is_dir():
        return None
    attente = D.demandes_en_attente()
    contenu = R.fichier_demandes(attente)
    cible = d / R.FICHIER_DEMANDES
    tmp = cible.with_suffix(".tmp")
    tmp.write_text(json.dumps(contenu, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, cible)
    D.marquer_envoyees([x["cle"] for x in attente if x["statut"] == "a_faire"])
    return len(attente)


def passage(athlete_id=None):
    """Un passage complet : importe les nouveaux paquets du dossier, puis écrit les demandes.
    Retourne {"importes": [(fichier, bilan)], "erreurs": [(fichier, message)], "demandes": n, "dossier": str}."""
    d = dossier()
    res = {"importes": [], "erreurs": [], "demandes": None, "dossier": str(d) if d else None}
    if not d:
        return res
    athlete_id = athlete_id or athlete_du_pont()
    if athlete_id is None:
        res["erreurs"].append(("", "Choisis le coureur qui reçoit les données des connecteurs."))
        return res
    for p in paquets_du_dossier(d):
        try:
            bilan = importer_fichier(p, athlete_id)
        except (R.ErreurConnecteurs, ValueError) as e:
            res["erreurs"].append((p.name, str(e)))
            continue
        if not bilan.get("deja"):
            res["importes"].append((p.name, bilan))
    try:
        res["demandes"] = ecrire_demandes(d)
    except OSError as e:
        res["erreurs"].append((R.FICHIER_DEMANDES, f"Écriture impossible : {e}"))
    definir_parametre(CLE_DERNIER_PASSAGE, datetime.now().isoformat(timespec="seconds"))
    return res


def dernier_passage():
    return obtenir_parametre(CLE_DERNIER_PASSAGE)


def texte_passage(res):
    if not res.get("dossier"):
        return "Aucun dossier de pont choisi."
    m = []
    for f, b in res["importes"]:
        m.append(f"{f} : {R.resume_paquet(b)}")
    if not res["importes"]:
        m.append("Aucun nouveau paquet.")
    if res.get("demandes"):
        m.append(f"{res['demandes']} demande(s) déposée(s) pour Claude.")
    for f, e in res["erreurs"]:
        m.append(f"⚠️ {f + ' : ' if f else ''}{e}")
    return " ".join(m)
