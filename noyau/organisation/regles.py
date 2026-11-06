"""
Règles de l'organisation d'un événement (étape 4.4), sans base ni Qt :
contrôle d'un dossier d'inscription selon la réglementation FFA des
manifestations running 2025-2026 (âge et distance, licence ou Pass
Prévention Santé, mineurs), tarif à payer, attribution des dossards,
chiffres de l'événement.

Réglementation FFA des manifestations running 2025-2026 (adoptée le
1er août 2025) :
  - III-A-3.1 distances maximales sur route : juniors 25 km, cadets 15 km,
    minimes 5 km, benjamins 3 km ; espoirs, seniors, masters sans limite ;
  - III-A-3.3 trail et montagne : poussins 1,5 km (75 m D+), benjamins 3 km
    (150 m), minimes 5 km (250 m) ; cadets et juniors limités en km-effort à
    la distance route de leur catégorie ; au-delà de 950 m de D+, juniors au
    minimum ;
  - II-A-3.1 à 3.3 licences acceptées : Athlé Compétition, Athlé Entreprise,
    Athlé Running (pas Santé ni Encadrement, pas Découverte pour un mineur) ;
    licences étrangères non acceptées ; autres fédérations seulement si
    reconnues par la FFA (à vérifier) ;
  - II-A-3.2 Pass Prévention Santé pour les majeurs non licenciés, fait au
    plus trois mois avant la course ;
  - II-A-3.4 mineurs non licenciés : questionnaire de santé rempli avec les
    parents et attestation parentale, ou certificat médical de moins de six
    mois.
Ces règles changent chaque saison : l'organisateur garde la décision
(chaque contrôle est un avertissement ou un manque, jamais un refus
automatique).
"""

from datetime import date

from noyau.club import categories as cat
from noyau.calendrier.regles import km_effort

STATUTS = (("en_attente", "En attente"), ("validee", "Validée"), ("liste_attente", "Liste d'attente"),
           ("annulee", "Annulée"), ("absent", "Absent au départ"))
LIBELLE_STATUT = dict(STATUTS)
JUSTIFICATIFS = (("licence_ffa", "Licence FFA"), ("pps", "Pass Prévention Santé"), ("certificat", "Certificat médical"),
                 ("questionnaire_mineur", "Questionnaire de santé (mineur)"), ("autre_federation", "Licence d'une autre fédération"))
LIBELLE_JUSTIFICATIF = dict(JUSTIFICATIFS)
LICENCES_ACCEPTEES = ("competition", "entreprise", "running")
DISTANCE_MAX_ROUTE = {"BE": 3, "MI": 5, "CA": 15, "JU": 25}
TRAIL_JEUNES = {"PO": (1.5, 75), "BE": (3, 150), "MI": (5, 250)}
TROP_JEUNES = ("BB", "EA")
DPLUS_JUNIORS_MIN = 950
DISCIPLINES_EPREUVE = (("route", "Route"), ("trail", "Trail"), ("montagne", "Course en montagne"), ("cross", "Cross"),
                       ("marche_nordique", "Marche nordique"), ("randonnee", "Randonnée, marche (non compétitive)"),
                       ("enfants", "Course enfants"))
LIBELLE_DISCIPLINE = dict(DISCIPLINES_EPREUVE)
STATUTS_EVENEMENT = (("brouillon", "Brouillon"), ("ouvert", "Inscriptions ouvertes"), ("complet", "Complet"),
                     ("clos", "Inscriptions closes"), ("termine", "Terminé"), ("annule", "Annulé"))
LIBELLE_STATUT_EVENEMENT = dict(STATUTS_EVENEMENT)


def _jour(d):
    if d is None or isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d)[:10])
    except ValueError:
        return None


def age_le(date_naissance, jour):
    n, j = _jour(date_naissance), _jour(jour)
    if not n or not j:
        return None
    return j.year - n.year - ((j.month, j.day) < (n.month, n.day))


def mois_entre(debut, fin):
    """Nombre de mois (décimal) entre deux dates."""
    a, b = _jour(debut), _jour(fin)
    return (b - a).days / 30.44 if a and b else None


def controle_age(epreuve, date_naissance, jour_course):
    """(manques, avertissements) liés à l'âge et à la distance de l'épreuve."""
    manques, avert = [], []
    if epreuve.get("discipline") in ("randonnee",) or not epreuve.get("competitive", 1):
        return manques, avert
    if not date_naissance:
        return ["date de naissance"], avert
    c = cat.categorie(date_naissance, cat.saison_de(jour_course))
    code = c["code"]
    if epreuve.get("categorie_min") and cat.ORDRE.get(code, 0) < cat.ORDRE.get(epreuve["categorie_min"], 0):
        manques.append(f"épreuve ouverte à partir de {cat.LIBELLE[epreuve['categorie_min']]} ({c['libelle']})")
    d, dp = epreuve.get("distance_km") or 0, epreuve.get("denivele_m") or 0
    if epreuve.get("discipline") == "enfants":
        return manques, avert
    if code in TROP_JEUNES:
        manques.append(f"{c['libelle']} : pas de course de ce type prévue par la réglementation")
        return manques, avert
    if epreuve.get("discipline") in ("trail", "montagne"):
        ke = km_effort(d, dp) or d
        if code in TRAIL_JEUNES:
            dmax, dpmax = TRAIL_JEUNES[code]
            if d > dmax or dp > dpmax:
                manques.append(f"{c['libelle']} : {dmax:g} km et {dpmax} m D+ au plus en trail")
        elif code in ("CA", "JU") and ke > DISTANCE_MAX_ROUTE[code]:
            manques.append(f"{c['libelle']} : {DISTANCE_MAX_ROUTE[code]} km-effort au plus (ici {ke:g})")
        if dp > DPLUS_JUNIORS_MIN and cat.ORDRE.get(code, 0) < cat.ORDRE["JU"]:
            manques.append(f"plus de {DPLUS_JUNIORS_MIN} m D+ : juniors au minimum")
    else:
        if code == "PO" and d > 1.5:
            avert.append("poussins sur route : voir le tableau des distances de cross de la réglementation")
        elif code in DISTANCE_MAX_ROUTE and d > DISTANCE_MAX_ROUTE[code]:
            manques.append(f"{c['libelle']} : {DISTANCE_MAX_ROUTE[code]} km au plus sur route")
    return manques, avert


def controle_sante(i, jour_course, pps_validite_mois=3):
    """(manques, avertissements) pour le justificatif de santé ou la licence."""
    manques, avert = [], []
    mineur = (age_le(i.get("date_naissance"), jour_course) or 99) < 18
    j = i.get("justificatif")
    if not j:
        manques.append("licence ou " + ("questionnaire de santé ou certificat" if mineur else "Pass Prévention Santé"))
        return manques, avert
    if j == "licence_ffa":
        if not (i.get("numero_licence") or "").strip():
            manques.append("numéro de licence")
        t = i.get("type_licence")
        if t and t not in LICENCES_ACCEPTEES:
            manques.append(f"licence {cat.LIBELLE_LICENCE.get(t, t)} non acceptée pour courir (Compétition, Running ou "
                           "Entreprise)")
        elif not t:
            avert.append("type de licence à vérifier (Compétition, Running ou Entreprise)")
    elif j == "pps":
        if mineur:
            manques.append("le Pass Prévention Santé est réservé aux majeurs")
        elif not i.get("pps_date"):
            manques.append("date du Pass Prévention Santé")
        else:
            m = mois_entre(i["pps_date"], jour_course)
            if m is not None and (m > pps_validite_mois or m < -0.1):
                manques.append(f"Pass Prévention Santé fait plus de {pps_validite_mois} mois avant la course")
    elif j == "certificat":
        if not i.get("certificat_date"):
            manques.append("date du certificat médical")
        elif mineur and (mois_entre(i["certificat_date"], jour_course) or 0) > 6:
            manques.append("certificat médical de plus de six mois")
        elif not mineur:
            avert.append("majeur non licencié : la réglementation demande le Pass Prévention Santé")
    elif j == "questionnaire_mineur":
        if not mineur:
            manques.append("questionnaire réservé aux mineurs : Pass Prévention Santé pour un majeur")
        elif not i.get("questionnaire_mineur"):
            manques.append("attestation parentale du questionnaire de santé")
    elif j == "autre_federation":
        avert.append(f"licence {i.get('federation') or 'd une autre fédération'} : vérifier qu'elle est reconnue par la FFA")
        if not (i.get("numero_licence") or "").strip():
            manques.append("numéro de licence")
    if j != "pps" and not i.get("justificatif_valide"):
        avert.append("pièce à contrôler")
    return manques, avert


def dossier(i, epreuve, evenement):
    """Contrôle complet d'une inscription : {complet, manques, avertissements, mineur, categorie}."""
    jour = epreuve.get("date") or evenement.get("date_debut")
    m1, a1 = controle_age(epreuve, i.get("date_naissance"), jour)
    m2, a2 = ([], []) if epreuve.get("discipline") == "randonnee" or not epreuve.get("competitive", 1) else \
        controle_sante(i, jour, evenement.get("pps_validite_mois") or 3)
    manques, avert = m1 + m2, a1 + a2
    age = age_le(i.get("date_naissance"), jour)
    mineur = age is not None and age < 18
    if mineur and evenement.get("autorisation_parentale", 1) and not i.get("autorisation_parentale"):
        manques.append("autorisation parentale")
    if (i.get("montant") or 0) > (i.get("montant_paye") or 0) + 0.005:
        manques.append(f"paiement : reste {(i['montant'] - (i.get('montant_paye') or 0)):.2f} €".replace(".", ","))
    if not i.get("contact_urgence_tel"):
        avert.append("pas de téléphone à prévenir")
    if i.get("nationalite") and i["nationalite"].strip().lower() not in ("fr", "fra", "france", "française", "francaise") \
            and i.get("justificatif") == "licence_ffa" and not (i.get("numero_licence") or "").strip():
        avert.append("participant étranger : licence étrangère non acceptée, Pass Prévention Santé ou certificat en français")
    c = cat.categorie(i.get("date_naissance"), cat.saison_de(jour)) if i.get("date_naissance") else None
    return {"complet": not manques, "manques": manques, "avertissements": avert, "mineur": mineur,
            "categorie": c}


def tarif(epreuve, licencie_ffa=False, jour_inscription=None, date_tarif_tardif=None):
    """Prix à payer : tarif licencié si prévu, tarif tardif après la date prévue."""
    j, t = _jour(jour_inscription) or date.today(), _jour(date_tarif_tardif)
    if t and j >= t and epreuve.get("tarif_tardif") is not None:
        return float(epreuve["tarif_tardif"])
    if licencie_ffa and epreuve.get("tarif_licencie") is not None:
        return float(epreuve["tarif_licencie"])
    return float(epreuve.get("tarif") or 0)


def chevauchements(epreuves):
    """Plages de dossards qui se chevauchent entre épreuves : [(nom a, nom b)]."""
    res = []
    p = [(e["nom"], e["dossard_debut"], e["dossard_fin"]) for e in epreuves if e.get("dossard_debut") and e.get("dossard_fin")]
    for i, (na, a0, a1) in enumerate(p):
        for nb, b0, b1 in p[i + 1:]:
            if a0 <= b1 and b0 <= a1:
                res.append((na, nb))
    return res


def numeros_libres(debut, fin, pris):
    pris = set(pris)
    return (n for n in range(int(debut), int(fin) + 1) if n not in pris)


def chiffres(inscriptions, epreuves):
    """Chiffres de l'événement par épreuve et au total."""
    par = {e["id"]: {"epreuve": e["nom"], "quota": e.get("quota"), "inscrits": 0, "valides": 0, "attente": 0,
                     "incomplets": 0, "femmes": 0, "hommes": 0, "recette": 0.0, "reste": 0.0, "dossards": 0}
           for e in epreuves}
    clubs, categories = {}, {}
    for i in inscriptions:
        p = par.get(i["epreuve_id"])
        if p is None or i["statut"] == "annulee":
            continue
        p["inscrits"] += 1
        p["valides"] += i["statut"] == "validee"
        p["attente"] += i["statut"] == "liste_attente"
        p["incomplets"] += not i["dossier"]["complet"]
        p["femmes"] += (i.get("sexe") or "")[:1] == "F"
        p["hommes"] += (i.get("sexe") or "")[:1] == "H"
        p["recette"] += i.get("montant_paye") or 0
        p["reste"] += max(0, (i.get("montant") or 0) - (i.get("montant_paye") or 0))
        p["dossards"] += bool(i.get("dossard"))
        clubs[i.get("club") or "Sans club"] = clubs.get(i.get("club") or "Sans club", 0) + 1
        k = i["dossier"]["categorie"]["code"] if i["dossier"]["categorie"] else "?"
        categories[k] = categories.get(k, 0) + 1
    for p in par.values():
        p["places"] = (p["quota"] - p["inscrits"]) if p["quota"] else None
        p["recette"], p["reste"] = round(p["recette"], 2), round(p["reste"], 2)
    total = {k: sum(p[k] for p in par.values()) for k in ("inscrits", "valides", "attente", "incomplets", "femmes",
                                                          "hommes", "recette", "reste", "dossards")}
    total["recette"], total["reste"] = round(total["recette"], 2), round(total["reste"], 2)
    return {"epreuves": list(par.values()), "total": total,
            "clubs": dict(sorted(clubs.items(), key=lambda x: -x[1])),
            "categories": dict(sorted(categories.items(), key=lambda x: cat.ORDRE.get(x[0], 99)))}
