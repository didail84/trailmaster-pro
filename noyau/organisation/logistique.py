"""
Logistique d'une course (étape 4.6), sans Qt ni SQL :

- démarches et rétroplanning : la liste des démarches d'après le contexte de
  la course (voie publique, communes, chronométrage, Natura 2000, forêt,
  terrains privés, parc, buvette, musique, tombola…), avec leur date limite
  calculée depuis la date de la course ;
- dimensionnement indicatif du poste de secours pour le public (grille de
  l'arrêté du 7 novembre 2006, référentiel national DPS) ;
- bénévoles : postes types, besoins suggérés, contrôles (trous, conflits
  d'horaires, signaleurs majeurs avec permis) ;
- ravitaillements : quantités indicatives selon le nombre de coureurs ;
- matériel : liste type et quantités suggérées ;
- partenaires et budget : avantage fiscal du mécénat, bilan, seuil de
  rentabilité ;
- courriers types.

Les règles sont des rappels à jour de novembre 2026 (code du sport,
référentiel DPS, réglementation buvettes, mécénat) : l'organisateur vérifie
toujours auprès de la mairie, de la préfecture et de la fédération.
"""

import math
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------- contexte

CONTEXTE_DEFAUT = {
    "voie_publique": False, "communes": 1, "departements": 1, "chronometree": True, "participants": 0,
    "spectateurs": 0, "natura2000": False, "foret_publique": False, "terrains_prives": False,
    "parc_naturel": False, "parc_national": False, "site_protege": False, "buvette": False,
    "buvette_alcool": False, "restauration": False, "musique": False, "tombola": False, "prix_total": 0,
    "course_ffa": True, "subventions": False, "nuit": False, "carrefours": 0, "gobelets_fournis": False,
    "dps_activite": 0.35, "dps_environnement": 0.40, "dps_delai": 0.30, "departement": "",
}

QUESTIONS = (
    ("voie_publique", "Le parcours emprunte des routes ou rues ouvertes à la circulation"),
    ("communes", "Nombre de communes traversées"),
    ("departements", "Nombre de départements traversés"),
    ("chronometree", "Course chronométrée avec classement (compétition)"),
    ("course_ffa", "Course inscrite au calendrier FFA"),
    ("participants", "Coureurs attendus (toutes épreuves)"),
    ("spectateurs", "Public attendu (accompagnants, spectateurs)"),
    ("carrefours", "Carrefours ou traversées de route à garder"),
    ("natura2000", "Passage dans un site Natura 2000"),
    ("foret_publique", "Passage en forêt domaniale ou communale (ONF)"),
    ("terrains_prives", "Passage sur des terrains privés"),
    ("parc_naturel", "Passage dans un Parc naturel régional"),
    ("parc_national", "Passage dans le cœur d'un Parc national"),
    ("site_protege", "Site classé, réserve naturelle ou arrêté de biotope"),
    ("nuit", "Course ou partie de course de nuit"),
    ("buvette", "Buvette"),
    ("buvette_alcool", "Buvette avec boissons alcoolisées"),
    ("restauration", "Repas ou restauration vendus"),
    ("musique", "Musique diffusée (sono, DJ, groupe)"),
    ("tombola", "Tombola ou loterie"),
    ("prix_total", "Total des prix en argent ou en bons (€)"),
    ("subventions", "Demande de subventions (commune, département, région)"),
    ("gobelets_fournis", "Gobelets fournis aux ravitaillements (sinon gobelet personnel obligatoire)"),
)

# départements où l'accès aux massifs est réglementé en été (risque incendie)
DEPARTEMENTS_FEUX = {"04", "05", "06", "07", "11", "13", "26", "2A", "2B", "30", "34", "48", "66", "83", "84"}
CARTES_FEUX = {"84": "https://www.risque-prevention-incendie.fr/vaucluse/",
               "13": "https://www.bouches-du-rhone.gouv.fr/",
               "83": "https://www.risque-prevention-incendie.fr/var/",
               "04": "https://www.risque-prevention-incendie.fr/alpes-de-haute-provence/",
               "06": "https://www.risque-prevention-incendie.fr/alpes-maritimes/"}
PARCS_REGIONAUX = {"84": "Mont-Ventoux, Luberon", "04": "Luberon, Verdon, Baronnies provençales",
                   "05": "Baronnies provençales, Queyras", "06": "Préalpes d'Azur", "13": "Alpilles, Camargue, Sainte-Baume",
                   "83": "Verdon, Sainte-Baume", "26": "Baronnies provençales, Vercors"}
PARCS_NATIONAUX = {"05": "Écrins", "06": "Mercantour", "04": "Mercantour", "13": "Calanques", "83": "Port-Cros",
                   "48": "Cévennes", "30": "Cévennes"}


def contexte(brut=None, evenement=None, epreuves=None):
    """Contexte complet (valeurs par défaut pour ce qui manque). Le département vient du code postal de l'événement,
    les participants des quotas si rien n'est saisi."""
    c = dict(CONTEXTE_DEFAUT)
    c.update({k: v for k, v in (brut or {}).items() if k in CONTEXTE_DEFAUT and v is not None})
    if not c["departement"] and evenement and evenement.get("code_postal"):
        cp = str(evenement["code_postal"])
        c["departement"] = cp[:2]
    if not c["participants"] and epreuves:
        c["participants"] = sum(int(e.get("quota") or 0) for e in epreuves)
    for k in ("communes", "departements", "participants", "spectateurs", "carrefours"):
        c[k] = max(0, int(c[k] or 0))
    c["communes"] = max(1, c["communes"])
    c["departements"] = max(1, c["departements"])
    c["prix_total"] = float(c["prix_total"] or 0)
    return c


# ---------------------------------------------------------------- démarches

CATEGORIES = ("Administratif", "Fédération", "Sécurité", "Environnement", "Buvette et animations", "Bénévoles",
              "Logistique", "Communication", "Après la course")
STATUTS = (("a_faire", "À faire"), ("en_cours", "En cours"), ("envoye", "Envoyé"), ("accorde", "Accordé / fait"),
           ("refuse", "Refusé"), ("sans_objet", "Sans objet"))
LIBELLE_STATUT = dict(STATUTS)
FINIS = ("accorde", "sans_objet")


def _d(c, k):
    return c.get("departement") or ""


def _catalogue(c):
    """(code, titre, catégorie, autorité, pièces, jours avant la course (négatif : après), condition, note)."""
    vp, chrono, multi = c["voie_publique"], c["chronometree"], c["communes"] > 1
    dep = _d(c, "departement")
    plusieurs_dep = c["departements"] > 1
    delai_decl = 90 if plusieurs_dep else 60
    autorite_decl = ("Préfet de chaque département traversé" if plusieurs_dep else
                     "Préfet du département" if multi else "Maire de la commune")
    parcs = PARCS_REGIONAUX.get(dep, "")
    return [
        ("reglement", "Rédiger le règlement de la course", "Administratif", "Organisateur",
         "Épreuves, âges et justificatifs (licence ou PPS), barrières horaires, matériel obligatoire, abandon, "
         "remboursement, droit à l'image, données personnelles (RGPD)", 150, True,
         "Le règlement est joint à la déclaration et affiché sur le site des inscriptions."),
        ("rgpd", "Données personnelles des inscrits et des bénévoles", "Administratif", "Organisateur",
         "Mention d'information sur le formulaire, durée de conservation, droit d'accès et d'effacement", 150, True,
         "Ne garder que ce qui sert (santé et licence jusqu'après la course, contact d'urgence)."),
        ("ffa_calendrier", "Inscrire la course au calendrier FFA et obtenir l'avis fédéral", "Fédération",
         "FFA : commission départementale des courses hors stade (CDCHS)",
         "Fiche de la course, règlement, parcours, dispositif de secours", 120, c["course_ffa"] or (vp and chrono),
         "L'avis de la fédération délégataire est demandé pour toute course chronométrée sur la voie publique "
         "(code du sport). Le calendrier fédéral a ses propres dates limites : vérifie-les auprès du comité."),
        ("prix_federation", "Autorisation de la fédération (prix de plus de 3 000 €)", "Fédération", "FFA",
         "Demande d'autorisation, règlement, montant des prix", 90, c["prix_total"] > 3000,
         "Code du sport, art. L331-5 et R331-3 : course ouverte aux licenciés avec plus de 3 000 € de prix."),
        ("declaration", "Déclarer la manifestation sportive (Cerfa 15824*03)", "Administratif", autorite_decl,
         "Cerfa 15824*03, règlement, plan du parcours, horaires, avis FFA, dispositif de secours, attestation "
         "d'assurance, liste des signaleurs", delai_decl, vp and chrono,
         f"Course chronométrée sur la voie publique : {'3 mois' if plusieurs_dep else '2 mois'} avant "
         "(code du sport, art. R331-6 et suivants)."),
        ("declaration_rando", "Déclarer la randonnée sans classement (Cerfa 15825*02)", "Administratif",
         "Préfet du département" if multi else "Maire de la commune",
         "Cerfa 15825*02, parcours, horaires", 30, vp and not chrono and c["participants"] >= 100,
         "Sans chronométrage ni classement : déclaration 1 mois avant dès 100 participants."),
        ("mairies", "Informer chaque mairie traversée et obtenir l'accord pour les chemins communaux",
         "Administratif", "Mairies traversées", "Courrier, plan du parcours, date et horaires", 120, True,
         "Même sans voie publique : le maire a la police des chemins ruraux et peut prendre un arrêté."),
        ("arretes", "Demander les arrêtés de circulation et de stationnement", "Sécurité",
         "Mairies ; Département pour les routes départementales", "Plan des points de traversée, horaires, déviations",
         60, vp, "Prévoir panneaux, barrières et déviations ; affichage de l'arrêté avant la course."),
        ("assurance", "Assurance responsabilité civile de l'organisateur", "Administratif", "Assureur du club",
         "Attestation d'assurance pour la date de la course (organisateur, bénévoles, participants)", 75, True,
         "Obligatoire (code du sport, art. L331-9 et L321-1). Vérifier que les bénévoles sont couverts."),
        ("secours", "Poste de secours : convention avec une association agréée de sécurité civile", "Sécurité",
         "Croix-Rouge, Protection civile, FFSS ou autre association agréée",
         "Convention, dimensionnement (public : grille nationale ; coureurs : analyse de l'organisateur)", 90, True,
         "Les secours aux coureurs se dimensionnent à part de ceux du public (référentiel national DPS)."),
        ("medecin", "Médecin de course (et kinés à l'arrivée)", "Sécurité", "Médecin, association de secours",
         "Accord écrit, numéro joignable le jour J", 60, True,
         "Demandé pour les trails par la réglementation FFA des courses hors stade ; à confirmer avec le comité."),
        ("plan_secours", "Plan de secours : accès des secours à chaque point du parcours, PC course, numéros",
         "Sécurité", "Organisateur", "Carte des accès, points de rendez-vous, numéros (PC, médecin, secours)", 45,
         True, "Prévoir l'évacuation depuis chaque ravitaillement et les points éloignés."),
        ("sdis", "Informer le SDIS et la gendarmerie (ou la police)", "Sécurité", "SDIS, brigade de gendarmerie",
         "Date, parcours, horaires, plan de secours, contact du PC course", 30, True, ""),
        ("signaleurs", "Liste des signaleurs (majeurs, titulaires du permis de conduire) et leurs postes",
         "Sécurité", autorite_decl if vp else "Organisateur",
         "Liste nominative par poste (jointe à la déclaration, mise à jour avant la course)", 30, vp,
         "Les signaleurs portent un gilet haute visibilité et un panneau ; ils ne bloquent la circulation que si "
         "l'arrêté le prévoit."),
        ("natura2000", "Évaluation des incidences Natura 2000", "Environnement", "DDT (service environnement)",
         "Formulaire d'évaluation simplifiée, carte du parcours sur le site", 90, c["natura2000"],
         "Obligatoire pour les manifestations listées (liste nationale : titre national ou budget de plus de "
         "100 000 € ; listes locales du département) : vérifie la liste du département auprès de la DDT. "
         "Le dossier est joint à la déclaration."),
        ("onf", "Convention avec l'ONF (forêt domaniale ou communale)", "Environnement", "ONF, agence territoriale",
         "Demande, parcours, dates de balisage et débalisage", 120, c["foret_publique"],
         "L'ONF peut demander une redevance et fixer des conditions (période, balisage)."),
        ("proprietaires", "Autorisations écrites de passage des propriétaires privés", "Environnement",
         "Propriétaires", "Courrier avec plan et coupon d'accord signé", 90, c["terrains_prives"],
         "Sans accord écrit, le passage n'est pas autorisé : garder les coupons signés."),
        ("parc", f"Informer le Parc naturel régional{(' (' + parcs + ')') if parcs else ''}", "Environnement",
         "Parc naturel régional", "Parcours, dates, effectifs, balisage", 120, c["parc_naturel"],
         "Le Parc donne des recommandations : périodes sensibles (nidification), zones à éviter, balisage."),
        ("parc_national", f"Autorisation du Parc national{(' (' + PARCS_NATIONAUX[dep] + ')') if dep in PARCS_NATIONAUX else ''}",
         "Environnement", "Direction du Parc national", "Demande, parcours, effectifs", 150, c["parc_national"],
         "Dans le cœur d'un Parc national, les manifestations sportives sont soumises à autorisation."),
        ("site_protege", "Autorisation pour site classé, réserve naturelle ou arrêté de biotope", "Environnement",
         "DREAL, gestionnaire de la réserve", "Demande, parcours, effectifs", 120, c["site_protege"], ""),
        ("feux_repli", "Prévoir un parcours de repli (accès aux massifs réglementé l'été)", "Environnement",
         "Préfecture", "Parcours de repli hors massifs, règle d'annulation dans le règlement", 45,
         dep in DEPARTEMENTS_FEUX and c.get("_mois") in (6, 7, 8, 9),
         "De juin à septembre, la préfecture peut fermer les massifs la veille selon le niveau de danger."),
        ("feux_veille", "Consulter la carte du danger feux de forêt la veille", "Environnement", "Préfecture",
         CARTES_FEUX.get(dep, "Carte départementale du danger"), 1,
         dep in DEPARTEMENTS_FEUX and c.get("_mois") in (6, 7, 8, 9),
         "En cas de massif fermé : parcours de repli ou annulation."),
        ("buvette", "Autorisation de buvette temporaire", "Buvette et animations", "Maire de la commune",
         "Demande : date, horaires, boissons vendues", 90 if c["buvette_alcool"] else 30, c["buvette"],
         "Au moins 15 jours avant (3 mois pour l'alcool dans une enceinte sportive). 48 h au plus par autorisation, "
         "10 par an pour une association sportive agréée. Aucune boisson alcoolisée aux mineurs."),
        ("restauration", "Restauration : hygiène (chaîne du froid, traçabilité des produits)", "Buvette et animations",
         "Organisateur ; DDPP en cas de doute", "Liste des produits, fournisseurs, glacières", 30, c["restauration"], ""),
        ("sacem", "Déclarer la musique à la Sacem", "Buvette et animations", "Sacem", "Déclaration en ligne", 15,
         c["musique"], "Il existe des forfaits pour les associations."),
        ("tombola", "Autorisation de tombola (Cerfa 11823*03)", "Buvette et animations",
         "Maire de la commune du siège de l'association", "Cerfa 11823*03, statuts, affectation des fonds", 45,
         c["tombola"], "Lots en nature ou bons d'achat, pas d'argent. Mises de moins de 20 €."),
        ("subventions", "Dossiers de demande de subvention (Cerfa 12156)", "Administratif",
         "Commune, intercommunalité, département, région", "Cerfa 12156, budget prévisionnel, statuts, RIB", 180,
         c["subventions"], "Les collectivités ont des dates limites de dépôt, souvent en début d'année."),
        ("benevoles_appel", "Lancer l'appel aux bénévoles", "Bénévoles", "Organisateur", "Formulaire, postes, horaires",
         90, True, ""),
        ("benevoles_convocation", "Envoyer les convocations aux bénévoles (poste, horaire, lieu, consignes)",
         "Bénévoles", "Organisateur", "Fiches de poste", 10, True, ""),
        ("briefing", "Briefing des bénévoles et des signaleurs", "Bénévoles", "Organisateur",
         "Plan, consignes de sécurité, numéros", 2, True, ""),
        ("reconnaissance", "Reconnaissance complète du parcours", "Logistique", "Organisateur",
         "Trace GPX, points de balisage, accès des secours", 30, True, ""),
        ("materiel_reserver", "Réserver le matériel (prêts, locations)", "Logistique", "Mairies, comité, loueurs",
         "Liste du matériel", 60, True, ""),
        ("ravitos_commandes", "Commander les ravitaillements", "Logistique", "Fournisseurs, partenaires",
         "Liste de courses des ravitaillements", 14, True, ""),
        ("materiel_recuperer", "Récupérer le matériel prêté et le charger", "Logistique", "Organisateur",
         "Check-list du matériel", 2, True, ""),
        ("balisage", "Baliser le parcours", "Logistique", "Organisateur", "Rubalise, flèches, panneaux", 1, True,
         "Baliser au plus tôt la veille (ou selon l'accord de l'ONF et des propriétaires)."),
        ("communication", "Affiche, réseaux, presse locale", "Communication", "Organisateur",
         "Affiche avec les logos des partenaires", 90, True, ""),
        ("debalisage", "Débaliser et nettoyer le parcours", "Après la course", "Organisateur", "", -1, True,
         "Le jour même ou le lendemain : aucun déchet ni balisage ne reste."),
        ("materiel_rendre", "Rendre le matériel prêté", "Après la course", "Organisateur", "Check-list du matériel",
         -3, True, ""),
        ("resultats_ffa", "Publier les résultats et les transmettre à la FFA", "Après la course", "FFA",
         "Fichier des résultats", -3, c["course_ffa"], ""),
        ("remerciements", "Remercier bénévoles et partenaires ; envoyer les reçus fiscaux des dons", "Après la course",
         "Organisateur", "Reçus des dons, photos, résultats", -15, True, ""),
        ("bilan", "Bilan de la course : finances, sécurité, retours ; le transmettre aux mairies et partenaires",
         "Après la course", "Organisateur", "Budget réalisé", -30, True, ""),
    ]


def demarches_pour(date_course, ctx):
    """Démarches qui s'appliquent : [{code, titre, categorie, autorite, pieces, echeance, note, jours}]."""
    jour = date.fromisoformat(str(date_course)[:10])
    c = dict(ctx)
    c["_mois"] = jour.month
    res = []
    for code, titre, categorie, autorite, pieces, jours, cond, note in _catalogue(c):
        if not cond:
            continue
        res.append({"code": code, "titre": titre, "categorie": categorie, "autorite": autorite, "pieces": pieces,
                    "echeance": (jour - timedelta(days=jours)).isoformat(), "jours": jours, "note": note})
    return res


def etat_demarche(d, aujourdhui=None):
    """« faite », « en retard », « bientôt » (moins de 15 jours), « à venir »."""
    if d.get("statut") in FINIS:
        return "faite"
    if d.get("statut") == "refuse":
        return "refusée"
    if d.get("statut") == "envoye":
        return "envoyée, en attente"
    if not d.get("echeance"):
        return "à venir"
    a = aujourdhui or date.today()
    e = date.fromisoformat(d["echeance"][:10])
    if e < a:
        return "en retard"
    return "bientôt" if (e - a).days <= 15 else "à venir"


def bilan_demarches(demarches, aujourdhui=None):
    etats = [etat_demarche(d, aujourdhui) for d in demarches]
    return {"total": len(demarches), "faites": etats.count("faite"), "en_retard": etats.count("en retard"),
            "bientot": etats.count("bientôt"), "en_attente": etats.count("envoyée, en attente"),
            "refusees": etats.count("refusée")}


def jalon(echeance, date_course):
    """« J-60 », « J+3 »."""
    n = (date.fromisoformat(str(date_course)[:10]) - date.fromisoformat(str(echeance)[:10])).days
    return "Jour J" if n == 0 else (f"J-{n}" if n > 0 else f"J+{-n}")


# ---------------------------------------------------------------- secours (public)

NIVEAUX_ACTIVITE = ((0.25, "Public assis : cérémonie, réunion, restauration"),
                    (0.30, "Public debout : cérémonie, exposition, foire, restauration"),
                    (0.35, "Public debout : spectacle statique, rassemblement sportif"),
                    (0.40, "Public debout et dynamique : fête, danse, carnaval, défilé"))
NIVEAUX_ENVIRONNEMENT = ((0.25, "Structures permanentes, voies publiques aux accès dégagés"),
                         (0.30, "Structures provisoires, espace naturel ≤ 2 ha, brancardage 150 à 300 m"),
                         (0.35, "Espace naturel 2 à 5 ha, brancardage 300 à 600 m, pente"),
                         (0.40, "Espace naturel > 5 ha, brancardage > 600 m, accès difficiles"))
NIVEAUX_DELAI = ((0.25, "Secours publics en 10 min ou moins"), (0.30, "Entre 10 et 20 min"),
                 (0.35, "Entre 20 et 30 min"), (0.40, "Plus de 30 min"))


def dps(public, activite=0.35, environnement=0.40, delai=0.30):
    """Dimensionnement indicatif du dispositif pour le PUBLIC (grille nationale) :
    {effectif, indice, ris, dispositif, intervenants, texte}. Les secours aux coureurs se dimensionnent à part."""
    p1 = max(0, int(public or 0))
    p = p1 if p1 <= 100000 else 100000 + (p1 - 100000) / 2
    i = round(activite + environnement + delai, 2)
    ris = round(i * p / 1000, 3)
    n = math.ceil(ris - 1e-9)
    n += n % 2
    if ris <= 0.25:
        disp, n, txt = "aucun", 0, "Pas de dispositif préconisé pour le public : décision de l'autorité de police."
    elif ris <= 1.125:
        disp, n, txt = "PAPS", 2, "Point d'alerte et de premiers secours : 2 secouristes."
    elif ris <= 12:
        disp, n = "DPS-PE", max(4, n)
        txt = f"Dispositif de petite envergure : environ {n} intervenants."
    elif ris <= 36:
        disp, txt = "DPS-ME", f"Dispositif de moyenne envergure : environ {n} intervenants."
    else:
        disp, txt = "DPS-GE", f"Dispositif de grande envergure : environ {n} intervenants, en plusieurs postes."
    return {"effectif": p, "indice": i, "ris": ris, "dispositif": disp, "intervenants": n, "texte": txt}


# ---------------------------------------------------------------- bénévoles

TYPES_POSTE = (("signaleur", "Signaleur"), ("ravitaillement", "Ravitaillement"), ("retrait", "Retrait des dossards"),
               ("accueil", "Accueil, inscriptions"), ("depart_arrivee", "Départ et arrivée"), ("chrono", "Chrono"),
               ("balisage", "Balisage"), ("debalisage", "Débalisage"), ("serre_file", "Serre-file"),
               ("parking", "Parking"), ("buvette", "Buvette"), ("secours", "Liaison secours, PC course"),
               ("logistique", "Logistique, matériel"), ("animation", "Animation, photo"), ("autre", "Autre"))
LIBELLE_POSTE = dict(TYPES_POSTE)


def age(date_naissance, jour):
    if not date_naissance:
        return None
    n = date.fromisoformat(str(date_naissance)[:10])
    j = date.fromisoformat(str(jour)[:10])
    return j.year - n.year - ((j.month, j.day) < (n.month, n.day))


def _minutes(h):
    if not h:
        return None
    try:
        hh, mm = str(h)[:5].split(":")
        return int(hh) * 60 + int(mm)
    except ValueError:
        return None


def chevauche(a, b):
    """Deux postes (jour, heure_debut, heure_fin) qui se recouvrent."""
    if (a.get("jour") or "") != (b.get("jour") or ""):
        return False
    a1, a2, b1, b2 = (_minutes(a.get("heure_debut")), _minutes(a.get("heure_fin")), _minutes(b.get("heure_debut")),
                      _minutes(b.get("heure_fin")))
    if None in (a1, a2, b1, b2):
        return False
    return a1 < b2 and b1 < a2


def controle_benevoles(postes, benevoles, affectations, jour_course, voie_publique=False):
    """postes [{id, nom, type, besoin, jour, heure_debut, heure_fin}], benevoles [{id, nom, prenom, date_naissance,
    permis}], affectations [(poste_id, benevole_id)]. Renvoie {par_poste, manques, conflits, alertes, sans_poste,
    besoin, pourvus}."""
    bv = {b["id"]: b for b in benevoles}
    pa = {p["id"]: p for p in postes}
    par_poste = {p["id"]: [] for p in postes}
    par_benevole = {}
    for pid, bid in affectations:
        if pid in par_poste and bid in bv:
            par_poste[pid].append(bid)
            par_benevole.setdefault(bid, []).append(pid)
    manques = [{"poste": p["nom"], "poste_id": p["id"], "manque": int(p.get("besoin") or 0) - len(par_poste[p["id"]])}
               for p in postes if len(par_poste[p["id"]]) < int(p.get("besoin") or 0)]
    conflits, alertes = [], []
    nom = lambda b: f"{b.get('prenom') or ''} {b['nom']}".strip()
    for bid, pids in par_benevole.items():
        for i, x in enumerate(pids):
            for y in pids[i + 1:]:
                if chevauche({**pa[x], "jour": pa[x].get("jour") or jour_course},
                             {**pa[y], "jour": pa[y].get("jour") or jour_course}):
                    conflits.append(f"{nom(bv[bid])} : « {pa[x]['nom']} » et « {pa[y]['nom']} » en même temps")
        a = age(bv[bid].get("date_naissance"), jour_course)
        for pid in pids:
            if pa[pid].get("type") == "signaleur":
                if a is not None and a < 18:
                    alertes.append(f"{nom(bv[bid])} : signaleur mineur ({a} ans)")
                elif voie_publique and not bv[bid].get("permis"):
                    alertes.append(f"{nom(bv[bid])} : signaleur sans permis de conduire indiqué")
                elif a is None and voie_publique:
                    alertes.append(f"{nom(bv[bid])} : date de naissance manquante (signaleur majeur exigé)")
        if a is not None and a < 18 and not any(pa[pid].get("type") == "signaleur" for pid in pids):
            alertes.append(f"{nom(bv[bid])} : bénévole mineur ({a} ans), autorisation parentale à garder")
    besoin = sum(int(p.get("besoin") or 0) for p in postes)
    pourvus = sum(min(len(par_poste[p["id"]]), int(p.get("besoin") or 0)) for p in postes)
    return {"par_poste": par_poste, "par_benevole": par_benevole, "manques": manques, "conflits": conflits,
            "alertes": alertes, "sans_poste": [b for b in benevoles if b["id"] not in par_benevole],
            "besoin": besoin, "pourvus": pourvus}


def postes_suggeres(epreuves, ravitos, ctx, inscrits=0):
    """Postes types à créer d'après les épreuves, les ravitaillements et le contexte (aucun doublon par nom ici :
    l'appelant ignore ceux qui existent)."""
    res = []
    dep = min((e.get("heure_depart") or "08:00" for e in epreuves), default="08:00")
    def h(m):                                            # arrondi au quart d'heure
        m = min(23 * 60 + 45, max(0, int(round(m / 15.0)) * 15))
        return f"{m // 60:02d}:{m % 60:02d}"
    m0 = _minutes(dep) or 480
    duree_max = max((_duree_estimee(e) for e in epreuves), default=180)
    n = max(inscrits, ctx.get("participants") or 0)
    res.append({"nom": "Retrait des dossards", "type": "retrait", "heure_debut": h(m0 - 120), "heure_fin": h(m0 - 15),
                "besoin": max(2, math.ceil(n / 150)), "lieu": "Village départ"})
    res.append({"nom": "Départ et arrivée", "type": "depart_arrivee", "heure_debut": h(m0 - 60),
                "heure_fin": h(m0 + duree_max + 30), "besoin": 4, "lieu": "Arche"})
    res.append({"nom": "Chrono", "type": "chrono", "heure_debut": h(m0 - 30), "heure_fin": h(m0 + duree_max + 30),
                "besoin": 2, "lieu": "Arrivée"})
    res.append({"nom": "PC course, liaison secours", "type": "secours", "heure_debut": h(m0 - 60),
                "heure_fin": h(m0 + duree_max + 30), "besoin": 1, "lieu": "PC course"})
    for r in ravitos:
        k = r.get("km") or 0
        res.append({"nom": f"Ravitaillement {r['nom']}", "type": "ravitaillement", "heure_debut": h(m0 + int(k * 4) - 45),
                    "heure_fin": r.get("barriere_horaire") or h(m0 + int(k * 9) + 30),
                    "besoin": max(2, math.ceil(r.get("coureurs", n) / 120) + 1), "lieu": r.get("lieu") or f"km {k}",
                    "ravitaillement_id": r.get("id"), "km": k})
    for e in epreuves:
        res.append({"nom": f"Serre-files {e['nom']}", "type": "serre_file", "heure_debut": e.get("heure_depart") or dep,
                    "heure_fin": h((_minutes(e.get("heure_depart")) or m0) + _duree_estimee(e)), "besoin": 2,
                    "lieu": "Derrière le dernier coureur"})
    km_total = max((float(e.get("distance_km") or 0) for e in epreuves), default=0)
    if km_total:
        res.append({"nom": "Balisage (veille)", "type": "balisage", "besoin": max(2, math.ceil(km_total / 10) * 2),
                    "lieu": "Parcours", "jour_veille": True, "heure_debut": "09:00", "heure_fin": "17:00"})
        res.append({"nom": "Débalisage", "type": "debalisage", "besoin": max(2, math.ceil(km_total / 10) * 2),
                    "lieu": "Parcours", "heure_debut": h(m0 + duree_max), "heure_fin": h(m0 + duree_max + 240)})
    if ctx.get("carrefours"):
        res.append({"nom": "Signaleurs", "type": "signaleur", "besoin": int(ctx["carrefours"]),
                    "heure_debut": h(m0 - 15), "heure_fin": h(m0 + duree_max), "lieu": "Carrefours du parcours"})
    if (ctx.get("spectateurs") or 0) + n > 300:
        res.append({"nom": "Parking", "type": "parking", "besoin": 2, "heure_debut": h(m0 - 150), "heure_fin": h(m0)})
    if ctx.get("buvette"):
        res.append({"nom": "Buvette", "type": "buvette", "besoin": 3, "heure_debut": h(m0 - 60),
                    "heure_fin": h(m0 + duree_max + 60)})
    return res


def _duree_estimee(e):
    """Temps du dernier coureur estimé en minutes : 9 min par km-effort, au moins 1 h."""
    ke = float(e.get("distance_km") or 0) + float(e.get("denivele_m") or 0) / 100
    return max(60, int(ke * 9))


# ---------------------------------------------------------------- ravitaillements

TYPES_RAVITO = (("eau", "Eau seulement"), ("complet", "Complet (liquide et solide)"),
                ("chaud", "Complet et chaud (soupe, boissons chaudes)"), ("arrivee", "Arrivée"))
LIBELLE_RAVITO = dict(TYPES_RAVITO)
MARGE = 1.15


def quantites_ravito(type_ravito, coureurs, km=0, ete=False, gobelets=False, benevoles=0):
    """Quantités indicatives pour un ravitaillement : [(produit, quantité, unité)]. Repères de terrain courants
    (à ajuster après la première édition) : eau 0,4 à 0,5 L par coureur, plus en été ; solide à partir des
    ravitaillements complets ; arrondi au-dessus avec 15 % de marge."""
    n = max(0, int(coureurs or 0))
    if not n:
        return []
    chaleur = 1.5 if ete else 1.0
    long_ = 1.3 if (km or 0) >= 20 else 1.0
    q = []
    eau = 0.4 if type_ravito == "eau" else 0.5
    q.append(("Eau plate", math.ceil(n * eau * chaleur * MARGE + benevoles * 1.5), "L"))
    if type_ravito != "eau":
        q.append(("Eau gazeuse", math.ceil(n * 0.1 * chaleur * MARGE), "L"))
        q.append(("Boisson sucrée ou cola", math.ceil(n * 0.15 * MARGE), "L"))
        q.append(("Boisson énergétique (poudre)", round(n * 0.25 * 0.04 * MARGE, 1), "kg"))
        q.append(("Bananes", math.ceil(n / 3 * long_ * MARGE), "pièces"))
        q.append(("Oranges", math.ceil(n / 4 * long_ * MARGE), "pièces"))
        q.append(("Fruits secs, pâtes de fruits", round(n * 0.03 * long_ * MARGE, 1), "kg"))
        q.append(("Chocolat, biscuits", round(n * 0.025 * long_ * MARGE, 1), "kg"))
        q.append(("Salé : chips, crackers, bretzels", round(n * 0.025 * long_ * MARGE, 1), "kg"))
        if (km or 0) >= 20 or type_ravito in ("chaud", "arrivee"):
            q.append(("Fromage, saucisson", round(n * 0.03 * MARGE, 1), "kg"))
    if type_ravito == "chaud":
        q.append(("Soupe ou bouillon", math.ceil(n * 0.25 * MARGE), "L"))
        q.append(("Café, thé (boissons chaudes)", math.ceil(n * 0.15 * MARGE), "L"))
    if type_ravito == "arrivee":
        q.append(("Bière ou boisson de récupération", math.ceil(n * 0.25), "L"))
    q.append(("Gobelets", math.ceil(n * 1.5 * MARGE) if gobelets else 0, "pièces"))
    q.append(("Sacs poubelle (tri)", max(2, math.ceil(n / 100)), "pièces"))
    return [x for x in q if x[1] or x[0] == "Gobelets"]


def liste_de_courses(ravitos):
    """Additionne les quantités de plusieurs ravitaillements : {produit: (quantité, unité)}."""
    tot = {}
    for r in ravitos:
        for p, qte, u in r.get("quantites") or []:
            a, _u = tot.get(p, (0, u))
            tot[p] = (round(a + qte, 1), u)
    return tot


# ---------------------------------------------------------------- matériel

CATEGORIES_MATERIEL = ("Départ et arrivée", "Balisage", "Sécurité", "Ravitaillements", "Village", "Chrono",
                       "Communication", "Divers")
STATUTS_MATERIEL = (("a_trouver", "À trouver"), ("demande", "Demandé"), ("reserve", "Réservé"),
                    ("charge", "Chargé"), ("en_place", "En place"), ("rendu", "Rendu"))
LIBELLE_STATUT_MATERIEL = dict(STATUTS_MATERIEL)


def materiel_suggere(epreuves, ravitos, ctx, benevoles=0):
    """[(article, catégorie, quantité, unité)] : liste type à compléter."""
    km = sum(float(e.get("distance_km") or 0) for e in epreuves)
    car = int(ctx.get("carrefours") or 0)
    nr = len(ravitos)
    n = int(ctx.get("participants") or 0)
    m = [("Arche départ et arrivée", "Départ et arrivée", 1, "pièce"),
         ("Barrières", "Départ et arrivée", max(10, math.ceil(n / 20)), "pièces"),
         ("Sono et micro", "Départ et arrivée", 1, "pièce"),
         ("Podium, récompenses", "Départ et arrivée", 1, "lot"),
         ("Rubalise", "Balisage", max(2, math.ceil(km / 3)), "rouleaux de 100 m"),
         ("Flèches et panneaux de direction", "Balisage", max(10, math.ceil(km * 2) + car * 2), "pièces"),
         ("Piquets, colliers, agrafeuse", "Balisage", 1, "lot"),
         ("Panneaux kilométriques", "Balisage", max(1, math.ceil(km / 5)), "pièces"),
         ("Gilets haute visibilité", "Sécurité", max(car + 4, benevoles), "pièces"),
         ("Panneaux K10 ou drapeaux pour signaleurs", "Sécurité", car, "pièces"),
         ("Talkies-walkies ou téléphones de poste", "Sécurité", nr + 4, "pièces"),
         ("Trousse de premiers secours", "Sécurité", nr + 1, "pièces"),
         ("Couvertures de survie (réserve)", "Sécurité", max(10, nr * 5), "pièces"),
         ("Barnums, tentes", "Ravitaillements", nr + 2, "pièces"),
         ("Tables", "Ravitaillements", nr * 2 + 4, "pièces"),
         ("Jerricans d'eau 20 L", "Ravitaillements",
          sum(math.ceil(next((q for p, q, u in r.get("quantites") or [] if p == "Eau plate"), 0) / 20) for r in ravitos),
          "pièces"),
         ("Poubelles et sacs de tri", "Ravitaillements", nr * 2 + 4, "pièces"),
         ("Couteaux, planches, nappes", "Ravitaillements", nr, "lots"),
         ("Toilettes (sur place ou louées)", "Village", max(2, math.ceil(n / 150)), "pièces"),
         ("Tables et chaises du retrait des dossards", "Village", 4, "pièces"),
         ("Groupe électrogène ou rallonges", "Village", 1, "pièce"),
         ("Chronométrage (puces, tapis ou saisie)", "Chrono", 1, "lot"),
         ("Ordinateur du chrono, imprimante", "Chrono", 1, "lot"),
         ("Banderoles des partenaires", "Communication", 1, "lot"),
         ("Lampes frontales de réserve", "Divers", 4 if ctx.get("nuit") else 0, "pièces")]
    return [x for x in m if x[2]]


# ---------------------------------------------------------------- partenaires et budget

TYPES_PARTENAIRE = (("mecenat", "Mécénat (don)"), ("nature", "Mécénat en nature"),
                    ("parrainage", "Parrainage (sponsoring)"), ("subvention", "Subvention publique"),
                    ("media", "Partenaire média"))
LIBELLE_PARTENAIRE = dict(TYPES_PARTENAIRE)
STATUTS_PARTENAIRE = (("a_contacter", "À contacter"), ("contacte", "Contacté"), ("relance", "À relancer"),
                      ("accord", "Accord"), ("verse", "Versé / reçu"), ("refus", "Refus"))
LIBELLE_STATUT_PARTENAIRE = dict(STATUTS_PARTENAIRE)
CATEGORIES_RECETTE = ("Inscriptions", "Partenaires", "Subventions", "Buvette et restauration", "Tombola", "Autres")
CATEGORIES_DEPENSE = ("Chronométrage", "Secours et médecin", "Assurance", "Ravitaillements", "Récompenses et lots",
                      "Cadeaux coureurs (t-shirts…)", "Communication", "Location de matériel", "Sacem, droits",
                      "Fédération (redevances)", "Repas des bénévoles", "Divers")


def avantage_fiscal(montant, particulier=False, chiffre_affaires=None):
    """Réduction d'impôt du donateur (association d'intérêt général) :
    entreprise 60 % (40 % au-delà de 2 M€), plafond 20 000 € ou 0,5 % du chiffre d'affaires HT si plus élevé ;
    particulier 66 % dans la limite de 20 % du revenu imposable."""
    m = float(montant or 0)
    if particulier:
        return {"taux": 66, "reduction": round(m * 0.66, 2), "cout_reel": round(m * 0.34, 2),
                "plafond": "20 % du revenu imposable", "article": "article 200 du code général des impôts"}
    red = min(m, 2_000_000) * 0.60 + max(0, m - 2_000_000) * 0.40
    plafond = max(20000, (chiffre_affaires or 0) * 0.005)
    return {"taux": 60, "reduction": round(red, 2), "cout_reel": round(m - red, 2),
            "plafond": f"{plafond:,.0f} €".replace(",", " ") + " (20 000 € ou 0,5 % du chiffre d'affaires HT)",
            "article": "article 238 bis du code général des impôts"}


def controle_contreparties(montant, valeur_contreparties):
    """Mécénat : les contreparties doivent rester nettement disproportionnées (tolérance de l'administration :
    au plus 25 % du don). Renvoie None si c'est bon, sinon un avertissement."""
    m, v = float(montant or 0), float(valeur_contreparties or 0)
    if m and v > m * 0.25:
        return (f"Contreparties de {v:.0f} € pour un don de {m:.0f} € (plus de 25 %) : c'est plutôt du parrainage, "
                "avec une facture.")
    return None


def bilan_budget(lignes, recettes_inscriptions=0, partenaires=None, inscrits=0, inscriptions_prevues=None):
    """lignes [{sens, categorie, libelle, prevu, realise, par_coureur}] ; les inscriptions (prévu : coureurs
    attendus × tarif moyen ; réalisé : encaissé) et les partenaires (accords et versements) sont ajoutés
    automatiquement ; `inscrits` = coureurs attendus pour les dépenses par coureur."""
    rec = [dict(l) for l in lignes if l["sens"] == "recette"]
    dep = [dict(l) for l in lignes if l["sens"] == "depense"]
    rec.append({"sens": "recette", "categorie": "Inscriptions", "libelle": "Inscriptions (automatique)",
                "prevu": recettes_inscriptions if inscriptions_prevues is None else inscriptions_prevues,
                "realise": recettes_inscriptions, "auto": True})
    for p in partenaires or []:
        if p.get("statut") not in ("accord", "verse") or not (p.get("montant") or p.get("valeur_nature")):
            continue
        cat = "Subventions" if p.get("type") == "subvention" else "Partenaires"
        val = float(p.get("montant") or 0) + float(p.get("valeur_nature") or 0)
        rec.append({"sens": "recette", "categorie": cat, "libelle": f"{p['nom']} (automatique)", "prevu": val,
                    "realise": val if p.get("statut") == "verse" else None, "auto": True})
    for l in dep:
        if l.get("par_coureur"):
            l["prevu_total"] = float(l.get("prevu") or 0) * inscrits
        else:
            l["prevu_total"] = float(l.get("prevu") or 0)
    tot = lambda ls, k: round(sum(float(l.get(k) or 0) for l in ls), 2)
    r_p, r_r = tot(rec, "prevu"), tot(rec, "realise")
    d_p, d_r = round(sum(l["prevu_total"] for l in dep), 2), tot(dep, "realise")
    par = {}
    for l in rec + dep:
        k = (l["sens"], l.get("categorie") or "Divers")
        a = par.get(k, [0, 0])
        a[0] += float(l.get("prevu_total", l.get("prevu")) or 0)
        a[1] += float(l.get("realise") or 0)
        par[k] = a
    fixe = sum(l["prevu_total"] for l in dep if not l.get("par_coureur"))
    variable = sum(float(l.get("prevu") or 0) for l in dep if l.get("par_coureur"))
    autres = sum(float(l.get("prevu") or 0) for l in rec if l.get("categorie") != "Inscriptions")
    return {"recettes": rec, "depenses": dep, "recettes_prevues": r_p, "recettes_realisees": r_r,
            "depenses_prevues": d_p, "depenses_realisees": d_r, "solde_prevu": round(r_p - d_p, 2),
            "solde_realise": round(r_r - d_r, 2), "par_categorie": par, "fixe": round(fixe, 2),
            "variable_par_coureur": round(variable, 2), "autres_recettes": round(autres, 2)}


def seuil_rentabilite(fixe, variable_par_coureur, tarif_moyen, autres_recettes=0):
    """Nombre de coureurs pour équilibrer : (dépenses fixes - autres recettes) / (tarif moyen - coût par coureur)."""
    marge = float(tarif_moyen or 0) - float(variable_par_coureur or 0)
    besoin = float(fixe or 0) - float(autres_recettes or 0)
    if besoin <= 0:
        return 0
    if marge <= 0:
        return None
    return math.ceil(besoin / marge)


def numero_recu(annee, rang):
    return f"DON-{annee}-{rang:04d}"


# ---------------------------------------------------------------- courriers

COURRIERS = (("mairie", "Mairie : information et demande d'accord"), ("proprietaire", "Propriétaire : autorisation de passage"),
             ("onf", "ONF : demande de convention"), ("parc", "Parc naturel : information"),
             ("sdis", "SDIS et gendarmerie : information"), ("sponsor", "Entreprise : proposition de partenariat"),
             ("subvention", "Collectivité : demande de subvention"), ("remerciement", "Partenaire : remerciements"))
LIBELLE_COURRIER = dict(COURRIERS)


def _jour_fr(d):
    mois = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
            "décembre")
    jours = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
    x = date.fromisoformat(str(d)[:10])
    return f"{jours[x.weekday()]} {x.day} {mois[x.month - 1]} {x.year}"


def courrier(code, evenement, epreuves, club=None, destinataire=None, ctx=None):
    """Texte du courrier (objet, corps) ; ce qui manque est entre crochets."""
    club = club or {}
    d = destinataire or {}
    ev = evenement
    asso = club.get("nom") or "[nom de l'association]"
    signe = club.get("president") or "[nom du président ou de la présidente]"
    quand = _jour_fr(ev["date_debut"])
    lieu = ev.get("commune") or "[commune]"
    eps = ", ".join(f"{e['nom']} ({(e.get('distance_km') or 0):g} km{', ' + str(e['denivele_m']) + ' m D+' if e.get('denivele_m') else ''})"
                    for e in epreuves) or "[épreuves]"
    heure = min((e.get("heure_depart") or "" for e in epreuves if e.get("heure_depart")), default="[heure]")
    n = (ctx or {}).get("participants") or "[nombre]"
    nom_d = d.get("nom") or "[destinataire]"
    tete = f"{asso}\n{' '.join(x for x in (club.get('adresse'), club.get('code_postal'), club.get('ville')) if x) or '[adresse]'}\n" \
           f"{' · '.join(x for x in (club.get('email'), club.get('telephone')) if x) or '[contact]'}\n\n{nom_d}\n\n" \
           f"À {club.get('ville') or '[ville]'}, le {_jour_fr(date.today().isoformat())}\n\n"
    corps = {
        "mairie": (f"Objet : {ev['nom']}, {quand}",
                   f"Madame la Maire, Monsieur le Maire,\n\nL'association {asso} organise le {quand} le « {ev['nom']} », au "
                   f"départ de {lieu}, avec les épreuves suivantes : {eps}. Premier départ à {heure}, environ {n} coureurs "
                   "attendus.\n\nLe parcours emprunte des chemins et voies de votre commune (plan joint). Nous vous "
                   "demandons votre accord pour ce passage et, si besoin, un arrêté de circulation ou de stationnement "
                   "aux points indiqués sur le plan.\n\nLe balisage sera posé la veille et retiré le jour même ou le "
                   "lendemain ; les déchets seront ramassés. Le dispositif de secours, l'assurance et les signaleurs "
                   "sont détaillés dans le dossier joint.\n\nNous restons à votre disposition et vous prions d'agréer, "
                   "Madame la Maire, Monsieur le Maire, l'expression de nos salutations respectueuses."),
        "proprietaire": (f"Objet : demande d'autorisation de passage, {ev['nom']} du {quand}",
                         f"Madame, Monsieur,\n\nL'association {asso} organise le {quand} une course à pied nature, le "
                         f"« {ev['nom']} » ({eps}). Le tracé que nous proposons traverse une parcelle vous appartenant "
                         "[lieu-dit, références cadastrales], sur le chemin indiqué sur le plan joint.\n\nNous vous "
                         "demandons l'autorisation d'y faire passer les coureurs le jour de la course, de [heure] à "
                         "[heure], et d'y poser un balisage temporaire la veille. Nous nous engageons à retirer le "
                         "balisage, à ramasser les déchets et à remettre les lieux en état. Notre assurance couvre la "
                         "manifestation (attestation sur demande).\n\nMerci de nous retourner le coupon ci-dessous.\n\n"
                         "Avec nos remerciements, veuillez agréer, Madame, Monsieur, nos salutations distinguées.\n\n"
                         "------------------------------------------------------------\n"
                         f"Je soussigné(e) ……………………………, propriétaire de la parcelle ……………, autorise / n'autorise pas "
                         f"(rayer la mention inutile) le passage du « {ev['nom']} » le {quand}.\n"
                         "Conditions éventuelles : ……………………………………\nFait à ……………, le ……………    Signature :"),
        "onf": (f"Objet : demande de convention, {ev['nom']} du {quand}",
                f"Madame, Monsieur,\n\nL'association {asso} organise le {quand} le « {ev['nom']} » ({eps}, environ {n} "
                "coureurs). Le parcours traverse la forêt [nom de la forêt, domaniale ou communale], sur les pistes et "
                "sentiers indiqués sur la carte jointe.\n\nNous sollicitons une convention d'occupation temporaire pour "
                "le passage des coureurs et le balisage (pose la veille, retrait le lendemain au plus tard). Nous "
                "suivrons vos conditions (zones à éviter, période, redevance éventuelle).\n\nVeuillez agréer, Madame, "
                "Monsieur, nos salutations distinguées."),
        "parc": (f"Objet : information, {ev['nom']} du {quand}",
                 f"Madame, Monsieur,\n\nL'association {asso} organise le {quand} le « {ev['nom']} » ({eps}, environ {n} "
                 "coureurs) dans le périmètre du Parc. Vous trouverez ci-joint le tracé et nos mesures pour l'environnement "
                 "(balisage temporaire, ravitaillements sans gobelet jetable, ramassage des déchets, serre-files).\n\n"
                 "Nous serions heureux de connaître vos recommandations (secteurs sensibles, période de nidification, "
                 "capacité d'accueil) pour adapter le parcours.\n\nVeuillez agréer, Madame, Monsieur, nos salutations "
                 "distinguées."),
        "sdis": (f"Objet : information, {ev['nom']} du {quand}",
                 f"Madame, Monsieur,\n\nNous vous informons que l'association {asso} organise le {quand} le "
                 f"« {ev['nom']} » au départ de {lieu} ({eps}). Premier départ à {heure}, environ {n} coureurs.\n\n"
                 "Vous trouverez ci-joint le parcours, les points d'accès des secours, le dispositif de secours "
                 "([association agréée], médecin) et le numéro du PC course joignable toute la journée : [téléphone].\n\n"
                 "Veuillez agréer, Madame, Monsieur, nos salutations distinguées."),
        "sponsor": (f"Objet : proposition de partenariat, {ev['nom']} du {quand}",
                    f"Madame, Monsieur,\n\nL'association {asso} organise le {quand} à {lieu} le « {ev['nom']} » : {eps}, "
                    f"environ {n} coureurs et leurs accompagnants.\n\nNous cherchons des partenaires pour faire vivre cette "
                    "course. Deux formes sont possibles :\n- un don (mécénat) : il ouvre droit à une réduction d'impôt de "
                    "60 % pour une entreprise, si l'association est d'intérêt général ; nous délivrons un reçu fiscal ;\n"
                    "- un parrainage (sponsoring) : votre visibilité (logo sur l'affiche, le site, les dossards, banderole "
                    "à l'arrivée) contre facture.\n\nUn partenariat en nature (produits pour les ravitaillements, lots, "
                    "matériel) est aussi le bienvenu.\n\nNous serions ravis de vous présenter le projet.\n\nVeuillez "
                    "agréer, Madame, Monsieur, nos salutations distinguées."),
        "subvention": (f"Objet : demande de subvention, {ev['nom']} du {quand}",
                       f"Madame, Monsieur,\n\nL'association {asso} organise le {quand} à {lieu} le « {ev['nom']} » ({eps}, "
                       f"environ {n} coureurs). Cette course fait découvrir le territoire et réunit [nombre] bénévoles.\n\n"
                       "Nous sollicitons une subvention de [montant] € pour [objet : sécurité, ravitaillements, "
                       "accessibilité, jeunes…]. Vous trouverez ci-joint le dossier Cerfa 12156, le budget prévisionnel, "
                       "nos statuts et notre RIB.\n\nVeuillez agréer, Madame, Monsieur, nos salutations distinguées."),
        "remerciement": (f"Objet : merci pour le « {ev['nom']} »",
                         f"Madame, Monsieur,\n\nLe « {ev['nom']} » s'est tenu le {quand} : [nombre] coureurs à l'arrivée, "
                         "[nombre] bénévoles. Votre soutien y est pour beaucoup.\n\nVous trouverez ci-joint "
                         "[les résultats, quelques photos, le reçu fiscal de votre don].\n\nNous espérons vous retrouver "
                         "pour la prochaine édition. Avec tous nos remerciements,"),
    }
    objet, texte = corps[code]
    return objet, tete + objet + "\n\n" + texte + f"\n\n{signe}\nPour {asso}"
