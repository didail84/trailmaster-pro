"""
Modules activables de Trail Hub Center (étape 2.3, bloc 6 du Master Plan).

Chaque espace (Coureur, Club, Organisation, Analyse) est fait de modules
qu'on allume ou qu'on éteint dans Réglages > Modules : un coureur seul ne
voit pas le Club, un organisateur peut masquer ce qui ne lui sert pas.
Éteindre un module ne supprime aucune donnée : ses écrans disparaissent
du menu et de la palette de commandes, et reviennent quand on le rallume.

Ce registre est la seule liste des modules : le menu, la palette, les
Réglages et la page Claude la lisent. Ajouter un futur module = ajouter
une entrée ici (avec `disponible=False` tant qu'il n'est pas construit).
"""

from dataclasses import dataclass, field

from data.database import obtenir_parametre, definir_parametre
from noyau.outils.evenements import emettre, MODULES_MODIFIES

ESPACES = ("Noyau", "Coureur", "Club", "Organisation", "Analyse")


@dataclass(frozen=True)
class Module:
    code: str
    nom: str
    espace: str
    description: str
    ecrans: tuple = ()              # méthodes du menu principal (ouvrir_…) qui lui appartiennent
    obligatoire: bool = False       # ne peut pas être éteint
    disponible: bool = True         # False : prévu au Master Plan, pas encore construit
    etape: str = ""                 # étape du Master Plan où il arrive (si pas encore disponible)
    blocs: tuple = field(default=())  # numéros des blocs du Master Plan
    actif_par_defaut: bool = True


MODULES = (
    Module("noyau", "Noyau", "Noyau",
           "Personnes, profils coureurs, imports et synchro, réglages, sauvegardes.",
           ("ouvrir_athletes", "ouvrir_personnes", "ouvrir_reglages", "ouvrir_import_et_synchro"),
           obligatoire=True, blocs=(1, 2, 3, 7, 9)),
    Module("entrainement", "Entraînement", "Coureur",
           "Aujourd'hui, fil d'activité, tableau de bord, journal, sorties, plans, renforcement, "
           "analyses, performance trail, bilans.",
           ("ouvrir_aujourdhui", "ouvrir_fil_activite", "ouvrir_tableau_de_bord", "ouvrir_journal",
            "ouvrir_historique_activites", "ouvrir_planification", "ouvrir_renforcement",
            "ouvrir_analyses_et_forme", "ouvrir_performance_trail", "ouvrir_bilans_objectifs"),
           obligatoire=True, blocs=(10,)),
    Module("suivi", "Récupération, santé et matériel", "Coureur",
           "Poids, IMC, sommeil, blessures, carte du corps, soins, matériel, nutrition du quotidien, zones, objectifs.",
           ("ouvrir_suivi",), blocs=(11, 13)),
    Module("courses", "Courses et stratégie", "Coureur",
           "Courses à venir, résultats, roadbook, matériel obligatoire d'une course.",
           ("ouvrir_courses_calendrier", "ouvrir_resultats_courses", "ouvrir_materiel_course"), blocs=(15,)),
    Module("parcours", "Cartes, traces et photos", "Coureur",
           "Bibliothèque de traces GPX, cartes, création de parcours, photos des sorties.",
           ("ouvrir_cartes_et_traces", "ouvrir_photos"), blocs=(16,)),
    Module("direct", "Suivi en direct", "Coureur",
           "Ta position en direct par téléphone sur le Wi-Fi de la maison (premier pas vers Trail Live).",
           ("ouvrir_suivi_direct",)),
    Module("nutrition", "Alimentation", "Coureur",
           "Produits de course et Nutri-Score, fait maison (barres, gels, boissons), comparatif, tolérances "
           "et besoins par heure, fiches aliments.",
           ("ouvrir_alimentation",), blocs=(12,)),
    Module("meteo", "Météo", "Coureur", "Prévisions pour tes sorties (connexion Internet nécessaire).",
           ("ouvrir_meteo",)),
    Module("fractionne", "Fractionné piste", "Coureur",
           "Temps de passage depuis ta VMA, minuteur à bips, saisie des temps réels.",
           disponible=False, etape="3", blocs=(14,)),
    Module("club", "Gestion du club", "Club",
           "Licences FFA, adhésions, cotisations, présences, profils des licenciés, entraîneurs.",
           disponible=False, etape="4", blocs=(17, 18, 19), actif_par_defaut=False),
    Module("kids", "Kids", "Club",
           "École d'athlé : groupes par catégorie, carnet de progression, badges, espace parents.",
           disponible=False, etape="7", blocs=(20,), actif_par_defaut=False),
    Module("organisation", "Organisation de courses", "Organisation",
           "Événement, inscriptions, logistique et bénévoles, chrono, incidents, tableau de commandement.",
           disponible=False, etape="6", blocs=(21, 22, 23, 24, 26, 27), actif_par_defaut=False),
    Module("trail_live", "Trail Live", "Organisation",
           "Suivi des coureurs en direct sur carte, page publique pour les proches.",
           disponible=False, etape="6", blocs=(25,), actif_par_defaut=False),
    Module("photos_dossard", "Photos par dossard", "Organisation",
           "Photos d'une course retrouvées par numéro de dossard.",
           disponible=False, etape="7", blocs=(28,), actif_par_defaut=False),
    Module("analyse", "Analyse transversale", "Analyse",
           "Prévu ou réel, rapports du club et des événements.",
           disponible=False, etape="7", blocs=(29, 30), actif_par_defaut=False),
)

PAR_CODE = {m.code: m for m in MODULES}
_PAR_ECRAN = {e: m.code for m in MODULES for e in m.ecrans}


def _cle(code):
    return f"module_{code}"


def module(code):
    return PAR_CODE[code]


def est_actif(code):
    """Un module obligatoire est toujours actif ; un module pas encore construit, jamais."""
    m = PAR_CODE.get(code)
    if m is None:
        return False
    if m.obligatoire:
        return True
    if not m.disponible:
        return False
    valeur = obtenir_parametre(_cle(code))
    if valeur is None:
        return m.actif_par_defaut
    return valeur == "1"


def definir_actif(code, actif):
    m = PAR_CODE.get(code)
    if m is None:
        raise ValueError(f"Module inconnu : {code}")
    if m.obligatoire and not actif:
        raise ValueError(f"Le module « {m.nom} » ne peut pas être éteint.")
    if not m.disponible:
        raise ValueError(f"Le module « {m.nom} » arrive à l'étape {m.etape} : il n'est pas encore disponible.")
    definir_parametre(_cle(code), "1" if actif else "0")
    emettre(MODULES_MODIFIES, code=code, actif=bool(actif))


def module_de_l_ecran(nom_methode):
    """Code du module d'un écran du menu (méthode ouvrir_…), ou None s'il n'est rattaché à rien."""
    return _PAR_ECRAN.get(nom_methode)


def ecran_visible(nom_methode):
    """Un écran rattaché à aucun module reste toujours visible."""
    code = module_de_l_ecran(nom_methode)
    return code is None or est_actif(code)


def actifs():
    return [m.code for m in MODULES if est_actif(m.code)]


def par_espace():
    """[(espace, [modules])] dans l'ordre d'ESPACES."""
    return [(e, [m for m in MODULES if m.espace == e]) for e in ESPACES]
