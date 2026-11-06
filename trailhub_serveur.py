#!/usr/bin/env python3
"""
Serveur Trail Hub Center (étape 5) — à lancer sur le NAS ou un ordinateur toujours allumé.

    python3 trailhub_serveur.py --base /srv/trailhub/trail_hub.db --creer-admin didier
    python3 trailhub_serveur.py --base /srv/trailhub/trail_hub.db            # démarre (port 8770, HTTPS)

Aucune fenêtre : tout se règle ensuite depuis le logiciel de bureau (Outils > Serveur) avec le compte
administrateur. Voir packaging/serveur/LISEZ-MOI.md pour l'installation sur OpenMediaVault.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main(argv=None):
    p = argparse.ArgumentParser(description="Serveur Trail Hub Center")
    p.add_argument("--base", required=True, help="chemin de la base SQLite du serveur (créée si besoin)")
    p.add_argument("--port", type=int, default=8770)
    p.add_argument("--hote", default="0.0.0.0", help="adresse d'écoute (0.0.0.0 = tout le réseau local)")
    p.add_argument("--http", action="store_true", help="sans HTTPS (déconseillé, mots de passe en clair sur le réseau)")
    p.add_argument("--creer-admin", metavar="IDENTIFIANT", help="crée un compte administrateur puis s'arrête")
    p.add_argument("--reinitialiser", metavar="IDENTIFIANT", help="nouveau mot de passe provisoire pour ce compte")
    p.add_argument("--relais-miroir", metavar="ETIQUETTE", help="copie cette version GitHub (ex. V109) dans le Relais "
                                                                 "du club, puis s'arrête")
    p.add_argument("--canal", default="stable", help="canal Relais pour --relais-miroir : stable ou test")
    a = p.parse_args(argv)

    import data.database as db
    db.CHEMIN_BDD = Path(a.base).expanduser().resolve()
    db.CHEMIN_BDD.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TRAILHUB_SANS_ANALYSE_AUTO", "1")
    from noyau.serveur import serveur as S
    from noyau.donnees import comptes as dco
    S.preparer_base()

    if a.relais_miroir:
        from noyau.relais import client as RC
        try:
            l = RC.miroir(a.relais_miroir, db.CHEMIN_BDD.parent / "relais", a.canal)
        except Exception as e:
            print(f"Relais : {e}")
            return 2
        print(f"Relais : {len(l)} fichier(s) copiés. Dans le logiciel (Réglages, Mises à jour), adresse du Relais : "
              f"https://<NAS>:{a.port}/relais")
        return 0
    if a.creer_admin:
        m1 = getpass.getpass("Mot de passe (10 caractères au moins) : ")
        if m1 != getpass.getpass("Encore une fois : "):
            print("Les deux mots de passe sont différents.")
            return 2
        try:
            cid, _p = dco.creer_compte(a.creer_admin, a.creer_admin, mot_de_passe=m1)
        except dco.ErreurCompte as e:
            print(e)
            return 2
        dco.ajouter_role(cid, "admin")
        print(f"Compte administrateur « {a.creer_admin} » créé.")
        return 0
    if a.reinitialiser:
        c = next((x for x in dco.comptes() if x["identifiant"].lower() == a.reinitialiser.lower()), None)
        if not c:
            print("Compte introuvable.")
            return 2
        print(f"Mot de passe provisoire de {c['identifiant']} : {dco.reinitialiser_mot_de_passe(c['id'])}")
        return 0
    if not dco.a_un_admin():
        print("Aucun administrateur : lance d'abord  --creer-admin TON_IDENTIFIANT")
        return 2
    print(f"Base : {db.CHEMIN_BDD}")
    info = S.demarrer(a.port, not a.http, a.hote, en_fond=True)
    for u in info["adresses"]:
        print(f"Serveur ouvert : {u}   (téléphones : {u}/m/)")
    if info["empreinte"]:
        print(f"Empreinte du certificat (à comparer dans le logiciel de bureau) :\n  {info['empreinte']}")
    print("Ctrl+C pour arrêter.")
    try:
        import time
        while True:
            time.sleep(3600)
            dco.purger_sessions()
            dco.purger_journal()
    except KeyboardInterrupt:
        S.arreter()
    return 0


if __name__ == "__main__":
    sys.exit(main())
