"""
Rôles et droits du mode serveur (étape 5), sans SQL ni Qt.

Chaque rôle est donné à un compte pour une association (club_id), pour un
événement (evenement_id), ou pour tout (administrateur). Un rôle ouvre des
« domaines » (club, présences, organisation…) en lecture (r) ou en
écriture (rw). Une personne ne voit que les associations et les
événements de ses rôles.
"""

ROLES = (("admin", "Administrateur (tout le serveur)"), ("bureau", "Bureau de l'association"),
         ("entraineur", "Entraîneur"), ("organisateur", "Organisateur d'un événement"),
         ("benevole", "Bénévole d'un événement"), ("coureur", "Coureur, licencié"), ("parent", "Parent"))
LIBELLE_ROLE = dict(ROLES)
PORTEE = {"admin": None, "bureau": "club", "entraineur": "club", "organisateur": "evenement",
          "benevole": "evenement", "coureur": "club", "parent": "club"}

# domaine de chaque module de noyau/donnees exposé au logiciel de bureau
DOMAINES = {"club": "club", "agenda_club": "presences", "profils": "profils", "personnes": "personnes",
            "organisation": "organisation", "chrono": "chrono", "logistique": "logistique",
            "calendrier": "calendrier", "annuaire": "annuaire", "kids": "kids", "analyse": "analyse",
            "commandement": "commandement", "comptes": "comptes"}

DROITS = {
    "admin": "*",
    "bureau": {"club": "rw", "presences": "rw", "profils": "rw", "personnes": "rw", "organisation": "rw", "chrono": "rw",
               "logistique": "rw", "calendrier": "rw", "annuaire": "rw", "kids": "rw", "analyse": "r", "commandement": "rw"},
    "entraineur": {"club": "r", "presences": "rw", "profils": "rw", "personnes": "r", "organisation": "r",
                   "calendrier": "r", "annuaire": "r", "kids": "rw", "analyse": "r"},
    "organisateur": {"club": "r", "personnes": "r", "profils": "r", "organisation": "rw", "chrono": "rw",
                     "logistique": "rw", "calendrier": "rw", "annuaire": "r", "commandement": "rw", "analyse": "r"},
    "benevole": {},
    "coureur": {},
    "parent": {},
}

# pages web (téléphone) ouvertes par rôle
PAGES = {"admin": {"chrono", "appel", "poste", "incident", "commandement", "resultats", "kids"},
         "bureau": {"chrono", "appel", "poste", "incident", "commandement", "resultats", "kids"},
         "entraineur": {"appel", "kids", "resultats"},
         "organisateur": {"chrono", "poste", "incident", "commandement"},
         "benevole": {"chrono", "poste", "incident"},
         "coureur": {"resultats"},
         "parent": {"kids"}}

PREFIXES_LECTURE = ("lire", "liste", "obtenir", "chercher", "apercu", "bilan", "etat", "chiffres", "export", "texte",
                    "tableau", "controle", "planning", "signaleurs", "liste_de_courses", "prochain", "prochaines",
                    "sans_appel", "attendus", "assiduite", "par_groupe", "zone_du_club", "doublons", "compter",
                    "index_de", "fiche", "roles", "athlete_de", "personne_de", "age", "est_mineur", "contexte",
                    "tarif_moyen", "classement", "passages", "resultats", "profil", "records", "entraineurs",
                    "modeles", "modele", "diplomes", "seances", "seance", "series", "serie", "groupes", "membres",
                    "adhesion", "adhesions", "saisons", "tarifs", "clubs", "club", "section", "sections",
                    "evenement", "evenements", "epreuve", "epreuves", "inscription", "inscriptions", "demarches",
                    "benevoles", "postes", "affectations", "ravitaillements", "materiel", "partenaire", "partenaires",
                    "lignes_budget", "sources", "courses", "analyser", "normaliser", "carnet", "badges", "suivi",
                    "points", "incidents", "rapport", "comparaison", "historique", "lister", "evolution", "bilans")
# fonctions d'écriture même si leur nom ressemble à une lecture
ECRITURES = {"choisir_club", "choisir_section", "analyser_import"}


def est_lecture(fonction):
    """Une fonction de lecture : son nom est (ou commence par) un des mots de PREFIXES_LECTURE. Tout le reste
    est traité comme une écriture (par prudence)."""
    if fonction in ECRITURES or fonction.startswith("_"):
        return False
    return fonction in PREFIXES_LECTURE or any(fonction.startswith(p + "_") for p in PREFIXES_LECTURE)


def droit_domaine(role, domaine):
    d = DROITS.get(role, {})
    if d == "*":
        return "rw"
    return d.get(domaine, "")


def autorise(roles, domaine, ecriture, clubs_vises=(), evenements_vises=(), clubs_des_evenements=None):
    """roles : [{role, club_id, evenement_id}] ; clubs_vises / evenements_vises : ce que l'appel touche ;
    clubs_des_evenements : {evenement_id: club_id organisateur}. True si un rôle couvre tout ce qui est visé."""
    clubs_des_evenements = clubs_des_evenements or {}
    besoin = "rw" if ecriture else "r"

    def couvre(r, club=None, ev=None):
        if r["role"] == "admin":
            return True
        d = droit_domaine(r["role"], domaine)
        if besoin not in d and not (besoin == "r" and d == "rw"):
            return False
        if PORTEE.get(r["role"]) == "club":
            if ev is not None:
                return clubs_des_evenements.get(ev) == r.get("club_id") and r.get("club_id") is not None
            return club is None or club == r.get("club_id")
        if PORTEE.get(r["role"]) == "evenement":
            if club is not None:
                return False if ecriture else True          # lecture des infos du club organisateur
            return ev is None or ev == r.get("evenement_id")
        return True

    cibles = [("c", c) for c in clubs_vises] + [("e", e) for e in evenements_vises]
    if not cibles:
        return any(couvre(r) for r in roles)
    return all(any(couvre(r, club=v) if t == "c" else couvre(r, ev=v) for r in roles) for t, v in cibles)


def pages_autorisees(roles):
    p = set()
    for r in roles:
        p |= PAGES.get(r["role"], set())
    return p


def clubs_de(roles):
    """None = tous (administrateur)."""
    if any(r["role"] == "admin" for r in roles):
        return None
    return {r["club_id"] for r in roles if r.get("club_id")}


def evenements_de(roles):
    if any(r["role"] == "admin" for r in roles):
        return None
    return {r["evenement_id"] for r in roles if r.get("evenement_id")}
