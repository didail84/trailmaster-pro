"""
Données personnelles (étape 8, volet « obligations »), sans Qt.

Le club est « responsable de traitement » des données de ses adhérents,
coureurs, bénévoles et enfants. Ce module l'aide à tenir ses obligations
(RGPD) sans juriste à côté :

- le registre des traitements, écrit d'après les modules allumés ;
- des durées de conservation, et le nettoyage de ce qui les dépasse
  (positions GPS, photos, coordonnées des inscrits des courses passées,
  anciens adhérents à revoir) ;
- les demandes des personnes : copie de leurs données (accès, portabilité)
  et effacement, avec le délai d'un mois pour répondre ;
- les violations de données (fuite, perte, vol d'ordinateur) : registre et
  rappel des 72 heures pour prévenir la CNIL.

Ce sont des aides, pas un avis juridique : la CNIL (cnil.fr) publie les
guides de référence, notamment pour les associations.
"""

import json
from datetime import date, datetime, timedelta

from noyau.donnees import base

DUREES_DEFAUT = {           # mois
    "positions_gps": 1,      # suivi en direct : jusqu'à un mois après la course
    "photos": 12,            # photos de course : un an
    "inscrits": 12,          # coordonnées des inscrits d'une course (les résultats restent)
    "journal": 12,           # journal des accès du serveur
    "anciens_adherents": 36, # fiches sans adhésion depuis trois saisons : à revoir
}
LIBELLE_DUREE = {"positions_gps": "Positions GPS du suivi en direct", "photos": "Photos de course",
                 "inscrits": "Coordonnées des inscrits (e-mail, téléphone, contact d'urgence, santé)",
                 "journal": "Journal des accès du serveur", "anciens_adherents": "Anciens adhérents (à revoir)"}
TYPES_DEMANDE = (("acces", "Copie de ses données (accès, portabilité)"), ("rectification", "Correction"),
                 ("effacement", "Effacement"), ("opposition", "Opposition (photos, e-mails…)"))
LIBELLE_DEMANDE = dict(TYPES_DEMANDE)
DELAI_REPONSE_JOURS = 30
DELAI_CNIL_HEURES = 72


def _par(cle, defaut=None):
    l = base.lire_un("SELECT valeur FROM parametres_app WHERE cle=?", (cle,))
    return l[0] if l else defaut


def durees():
    return {k: int(_par(f"rgpd_duree_{k}") or v) for k, v in DUREES_DEFAUT.items()}


def regler_duree(cle, mois):
    if cle not in DUREES_DEFAUT or not 1 <= int(mois) <= 240:
        raise ValueError("Durée inconnue ou hors limites (1 à 240 mois).")
    base.ecrire("INSERT INTO parametres_app (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur",
                (f"rgpd_duree_{cle}", str(int(mois))))


# ------------------------------------------------------------------ registre

def registre(modules_actifs=None):
    """Les traitements du club : [{traitement, finalite, personnes, donnees, base_legale, destinataires, duree,
    securite}], d'après les modules allumés."""
    from noyau import modules as MO
    actifs = set(modules_actifs) if modules_actifs is not None else {m.code for m in MO.MODULES if MO.est_actif(m.code)}
    d = durees()
    secu = ("base sur l'ordinateur du club ou le NAS ; serveur en HTTPS, comptes nominatifs avec rôles, mots de passe "
            "protégés, journal des accès ; sauvegardes")
    t = []
    if "club" in actifs:
        t.append({"traitement": "Gestion des adhérents", "finalite": "adhésions, licences FFA, cotisations et reçus, "
                  "agenda et présences, résultats des licenciés", "personnes": "adhérents, parents des mineurs",
                  "donnees": "identité, coordonnées, date de naissance, licence, pièce de santé (type et date), "
                  "paiements, présences, résultats", "base_legale": "contrat (adhésion) ; obligation légale (licence)",
                  "destinataires": "bureau, entraîneurs de la section ; FFA pour la licence",
                  "duree": f"durée de l'adhésion, puis revue après {d['anciens_adherents']} mois sans adhésion ; "
                  "pièces comptables 10 ans", "securite": secu})
    if "kids" in actifs:
        t.append({"traitement": "École d'athlé (Kids)", "finalite": "carnet de progression, badges, espace parents",
                  "personnes": "enfants mineurs, parents", "donnees": "compétences validées, présences, tailles "
                  "d'équipement", "base_legale": "contrat (adhésion) avec accord parental",
                  "destinataires": "entraîneurs, parents de l'enfant seulement", "duree": "durée de l'adhésion",
                  "securite": secu + " ; aucun classement entre enfants"})
    if "organisation" in actifs:
        t.append({"traitement": "Organisation de courses", "finalite": "inscriptions, contrôle des dossiers FFA, dossards, "
                  "chrono et classements, bénévoles", "personnes": "coureurs inscrits, bénévoles",
                  "donnees": "identité, coordonnées, date de naissance, licence ou PPS, contact d'urgence, temps",
                  "base_legale": "contrat (inscription) ; obligation légale (réglementation FFA)",
                  "destinataires": "organisation ; chronométreur ; classements publiés",
                  "duree": f"coordonnées {d['inscrits']} mois après la course ; résultats conservés", "securite": secu})
    if "trail_live" in actifs:
        t.append({"traitement": "Jour de course et suivi en direct", "finalite": "sécurité des coureurs (PC course, "
                  "incidents), suivi par les proches", "personnes": "coureurs, bénévoles",
                  "donnees": "pointages, incidents (dont blessures), positions GPS", "base_legale":
                  "intérêt légitime (sécurité) ; consentement pour la position publique",
                  "destinataires": "PC course, secours ; proches (page publique sans position sans accord)",
                  "duree": f"positions {d['positions_gps']} mois ; incidents avec le dossier de la course",
                  "securite": secu})
    if "photos_dossard" in actifs:
        t.append({"traitement": "Photos par dossard", "finalite": "rendre à chaque coureur ses photos de course",
                  "personnes": "coureurs photographiés", "donnees": "photos, numéro de dossard lu (pas de "
                  "reconnaissance des visages)", "base_legale": "consentement (droit à l'image ; accord parental "
                  "pour un mineur)", "destinataires": "le coureur seul (dossard + code) ; tous les coureurs visibles "
                  "doivent être d'accord", "duree": f"{d['photos']} mois", "securite": secu + " ; EXIF retirées"})
    if "serveur" in actifs:
        t.append({"traitement": "Comptes et journal du serveur", "finalite": "accès du bureau, des entraîneurs et "
                  "bénévoles ; traçabilité", "personnes": "titulaires de comptes", "donnees": "identifiant, rôles, "
                  "adresse IP, actions", "base_legale": "intérêt légitime (sécurité)", "destinataires":
                  "administrateur", "duree": f"journal {d['journal']} mois", "securite": secu})
    return t


# ------------------------------------------------------------------ nettoyage

def _limite(mois, aujourdhui=None):
    j = aujourdhui or date.today()
    return (j - timedelta(days=int(mois * 30.44))).isoformat()


def a_nettoyer(aujourdhui=None):
    """Ce qui dépasse les durées : {clé: nombre}."""
    d = durees()
    res = {}
    try:
        res["positions_gps"] = base.lire_un("SELECT COUNT(*) FROM positions_live x JOIN evenements e ON e.id = x.evenement_id "
                                            "WHERE e.date_debut < ?", (_limite(d["positions_gps"], aujourdhui),))[0]
    except Exception:
        res["positions_gps"] = 0
    try:
        res["photos"] = base.lire_un("SELECT COUNT(*) FROM photos_course p JOIN evenements e ON e.id = p.evenement_id "
                                     "WHERE e.date_debut < ?", (_limite(d["photos"], aujourdhui),))[0]
    except Exception:
        res["photos"] = 0
    res["inscrits"] = base.lire_un(
        "SELECT COUNT(*) FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id JOIN evenements e ON e.id = p.evenement_id "
        "WHERE e.date_debut < ? AND (i.email IS NOT NULL OR i.telephone IS NOT NULL OR i.contact_urgence_tel IS NOT NULL "
        "OR i.pps_date IS NOT NULL OR i.certificat_date IS NOT NULL)", (_limite(d["inscrits"], aujourdhui),))[0]
    res["anciens_adherents"] = len(anciens_adherents(aujourdhui))
    return res


def nettoyer(cles, aujourdhui=None):
    """Supprime (ou rend anonyme) ce qui dépasse les durées, pour les clés choisies. Renvoie {clé: nombre}."""
    d = durees()
    fait = {}
    if "positions_gps" in cles:
        fait["positions_gps"] = base.ecrire_compte(
            "DELETE FROM positions_live WHERE evenement_id IN (SELECT id FROM evenements WHERE date_debut < ?)",
            (_limite(d["positions_gps"], aujourdhui),))
    if "photos" in cles:
        from noyau.donnees import photos as dph
        ids = [r[0] for r in base.lire_tous("SELECT p.id FROM photos_course p JOIN evenements e ON e.id = p.evenement_id "
                                            "WHERE e.date_debut < ?", (_limite(d["photos"], aujourdhui),))]
        for i in ids:
            dph.supprimer_photo(i)
        fait["photos"] = len(ids)
    if "inscrits" in cles:
        fait["inscrits"] = base.ecrire_compte(
            "UPDATE inscriptions SET email=NULL, telephone=NULL, contact_urgence_nom=NULL, contact_urgence_tel=NULL, "
            "pps_date=NULL, certificat_date=NULL, numero_licence=NULL, notes=NULL WHERE epreuve_id IN (SELECT p.id FROM "
            "epreuves p JOIN evenements e ON e.id = p.evenement_id WHERE e.date_debut < ?)",
            (_limite(d["inscrits"], aujourdhui),))
    return fait


def anciens_adherents(aujourdhui=None):
    """Fiches de personnes qui ont été adhérentes mais plus depuis la durée choisie, sans autre lien actif
    (profil coureur, compte, enfant d'un adhérent) : à revoir une par une, rien n'est effacé tout seul."""
    from noyau.club import categories as cat
    mois = durees()["anciens_adherents"]
    j = aujourdhui or date.today()
    saison_limite = cat.saison_de(date.fromisoformat(_limite(mois, j)))
    lignes = base.lire_tous(
        "SELECT p.id, p.nom, p.prenom, MAX(a.saison) FROM personnes p JOIN adhesions a ON a.personne_id = p.id "
        "GROUP BY p.id HAVING MAX(a.saison) < ? ORDER BY p.nom", (saison_limite,))
    res = []
    for pid, nom, prenom, s in lignes:
        if base.lire_un("SELECT 1 FROM athletes WHERE personne_id=?", (pid,)) if "personne_id" in _colonnes("athletes") else None:
            continue
        res.append({"personne_id": pid, "nom": nom, "prenom": prenom, "derniere_saison": s})
    return res


def _colonnes(table):
    return {r[1] for r in base.lire_tous(f"PRAGMA table_info({table})")}


# ------------------------------------------------------------------ demandes des personnes

def donnees_de(personne_id):
    """Tout ce que Trail Hub garde sur une personne (droit d'accès et portabilité), en dictionnaire JSON."""
    def lignes(sql, par=(personne_id,)):
        c = base.connexion()
        try:
            r = c.execute(sql, par)
            noms = [x[0] for x in r.description]
            return [dict(zip(noms, l)) for l in r.fetchall()]
        finally:
            c.close()
    blocs = {"fiche": "SELECT * FROM personnes WHERE id=?", "roles": "SELECT * FROM personnes_roles WHERE personne_id=?",
             "adhesions": "SELECT * FROM adhesions WHERE personne_id=?",
             "inscriptions": "SELECT * FROM inscriptions WHERE personne_id=?",
             "resultats": "SELECT * FROM resultats_licencies WHERE personne_id=?",
             "presences": "SELECT s.date, s.titre, x.statut FROM presences_club x JOIN seances_club s ON s.id = x.seance_id "
                          "WHERE x.personne_id=?",
             "consentements": "SELECT * FROM consentements WHERE personne_id=?",
             "carnet_kids": "SELECT c.libelle, v.date, v.valide_par FROM kids_validations v JOIN kids_competences c ON "
                            "c.id = v.competence_id WHERE v.personne_id=?",
             "badges_kids": "SELECT code, date FROM kids_badges WHERE personne_id=?",
             "photos": "SELECT p.nom_origine, p.prise_le, e.nom AS evenement FROM photos_dossards d JOIN photos_course p ON "
                       "p.id = d.photo_id JOIN evenements e ON e.id = p.evenement_id JOIN epreuves ep ON ep.evenement_id = "
                       "e.id JOIN inscriptions i ON i.epreuve_id = ep.id AND i.dossard = d.dossard WHERE i.personne_id=?"}
    res = {"export_du": datetime.now().isoformat(timespec="minutes"), "logiciel": "Trail Hub Center"}
    for k, sql in blocs.items():
        try:
            res[k] = lignes(sql)
        except Exception:
            res[k] = []
    for k in ("inscriptions", "adhesions"):
        for l in res[k]:
            l.pop("uuid", None)
    return res


def export_json(personne_id):
    return json.dumps(donnees_de(personne_id), ensure_ascii=False, indent=1, default=str)


def effacer_personne(personne_id):
    """Droit à l'effacement : la fiche, ses adhésions, consentements, carnet, présences, résultats sont supprimés ;
    ses inscriptions aux courses deviennent anonymes (les classements gardent une ligne « Anonyme »)."""
    if base.lire_un("SELECT 1 FROM athletes WHERE personne_id=?", (personne_id,)) if "personne_id" in _colonnes("athletes") \
            else None:
        raise ValueError("Cette personne a un profil coureur avec ses sorties : supprime-le d'abord dans l'écran Athlètes.")
    with base.transaction() as cur:
        cur.execute("UPDATE inscriptions SET personne_id=NULL, nom='Anonyme', prenom=NULL, email=NULL, telephone=NULL, "
                    "date_naissance=NULL, contact_urgence_nom=NULL, contact_urgence_tel=NULL, numero_licence=NULL, "
                    "notes=NULL, droit_image=0 WHERE personne_id=?", (personne_id,))
        cur.execute("DELETE FROM personnes WHERE id=?", (personne_id,))
    return True


def demandes():
    cles = ("id", "personne_id", "nom", "type", "recue_le", "traitee_le", "reponse")
    res = [dict(zip(cles, l)) for l in base.lire_tous(
        f"SELECT {', '.join(cles)} FROM rgpd_demandes ORDER BY traitee_le IS NOT NULL, recue_le DESC")]
    for d in res:
        d["echeance"] = (date.fromisoformat(d["recue_le"][:10]) + timedelta(days=DELAI_REPONSE_JOURS)).isoformat()
        d["en_retard"] = not d["traitee_le"] and d["echeance"] < date.today().isoformat()
    return res


def enregistrer_demande(type_, nom, personne_id=None, recue_le=None):
    if type_ not in LIBELLE_DEMANDE:
        raise ValueError("Type de demande inconnu.")
    if not (nom or "").strip():
        raise ValueError("Indique qui fait la demande.")
    return base.inserer("rgpd_demandes", {"personne_id": personne_id, "nom": nom.strip(), "type": type_,
                                          "recue_le": (recue_le or date.today().isoformat())[:10]})


def traiter_demande(demande_id, reponse):
    base.ecrire("UPDATE rgpd_demandes SET traitee_le=?, reponse=? WHERE id=?",
                (date.today().isoformat(), (reponse or "").strip() or None, demande_id))


# ------------------------------------------------------------------ violations

def incidents():
    cles = ("id", "constate_le", "description", "donnees", "personnes", "mesures", "cnil_le", "informees_le", "clos")
    res = [dict(zip(cles, l)) for l in base.lire_tous(f"SELECT {', '.join(cles)} FROM rgpd_incidents ORDER BY constate_le DESC")]
    for i in res:
        i["limite_cnil"] = (datetime.fromisoformat(i["constate_le"]) + timedelta(hours=DELAI_CNIL_HEURES)).isoformat(
            timespec="minutes")
    return res


def enregistrer_incident(champs, incident_id=None):
    v = {k: champs.get(k) for k in ("constate_le", "description", "donnees", "personnes", "mesures", "cnil_le",
                                    "informees_le", "clos") if k in champs}
    if incident_id is None:
        if not (v.get("description") or "").strip():
            raise ValueError("Décris ce qui s'est passé.")
        v.setdefault("constate_le", datetime.now().isoformat(timespec="minutes"))
        return base.inserer("rgpd_incidents", v)
    base.ecrire(f"UPDATE rgpd_incidents SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (incident_id,))
    return incident_id


CONDUITE_VIOLATION = (
    "Arrêter la fuite : changer les mots de passe, couper le partage, désactiver le compte ou l'ordinateur concerné.",
    "Noter tout dans ce registre : quand, quoi, combien de personnes, quelles données.",
    "Si un risque existe pour les personnes : prévenir la CNIL dans les 72 heures (notifications.cnil.fr).",
    "Si le risque est élevé (données de santé, mineurs, positions, mots de passe) : prévenir aussi les personnes.",
    "Même sans notification, la violation reste écrite dans ce registre.",
)
