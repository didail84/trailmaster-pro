"""
Règles des adhésions d'une saison (étape 4.1) : dossier complet ou pas,
alertes du club, chiffres de la saison. Aucune base ici : les fonctions
reçoivent les adhésions déjà lues (noyau/donnees/club.py).
"""

from collections import Counter

from noyau.club import categories as cat

STATUTS = (("en_cours", "En cours"), ("validee", "Validée"), ("annulee", "Annulée"))
LIBELLE_STATUT = dict(STATUTS)
SANTE = (("questionnaire", "Questionnaire de santé"), ("certificat", "Certificat médical"),
         ("pps", "Pass Prévention Santé"))
LIBELLE_SANTE = dict(SANTE)
MODES_PAIEMENT = ("Chèque", "Espèces", "Virement", "Carte bancaire", "HelloAsso", "Chèques vacances",
                  "Coupon sport", "Pass'Sport", "Autre")


def _fr(v, d=2):
    t = f"{v:,.{d}f}".replace(",", " ").replace(".", ",")
    return t[:-3] if t.endswith(",00") else t


def reste_a_payer(a):
    return max(0.0, (a.get("cotisation") or 0) - (a.get("montant_paye") or 0))


def dossier(a, saison=None):
    """a : une adhésion avec la personne (date_naissance, mineur…).
    Renvoie {complet, manques: [texte], avertissements: [texte]}."""
    manques, avert = [], []
    if a.get("statut") == "annulee":
        return {"complet": True, "manques": [], "avertissements": ["Adhésion annulée."]}
    typ = a.get("type_licence")
    if not typ:
        manques.append("type de licence")
    elif typ != "adherent" and not (a.get("numero_licence") or "").strip():
        manques.append("numéro de licence FFA")
    if not a.get("sante_type"):
        manques.append("pièce de santé (certificat ou questionnaire)")
    if a.get("mineur") and not a.get("autorisation_parentale"):
        manques.append("autorisation parentale")
    reste = reste_a_payer(a)
    if (a.get("cotisation") or 0) <= 0:
        manques.append("montant de la cotisation")
    elif reste > 0.005:
        manques.append(f"cotisation : reste {_fr(reste)} €")
    if not a.get("date_naissance"):
        avert.append("date de naissance inconnue : pas de catégorie")
    elif typ:
        m = cat.licence_possible(typ, a["date_naissance"], saison or a.get("saison"))
        if m:
            avert.append(m)
    if a.get("mineur") and a.get("droit_image") is None:
        avert.append("droit à l'image non renseigné")
    return {"complet": not manques, "manques": manques, "avertissements": avert}


def chiffres(adhesions, precedentes=None, saison=None):
    """Chiffres d'une saison : effectif, par catégorie, sexe, licence, groupe ; dossiers incomplets ;
    cotisations ; renouvellements par rapport à la saison précédente."""
    actives = [a for a in adhesions if a.get("statut") != "annulee"]
    cats = Counter()
    for a in actives:
        c = cat.categorie(a.get("date_naissance"), saison or a.get("saison"))
        cats[c["code"] if c else "?"] += 1
    sexes = Counter((a.get("sexe") or "?").upper()[:1] or "?" for a in actives)
    licences = Counter(a.get("type_licence") or "?" for a in actives)
    incomplets = [a for a in actives if not dossier(a, saison)["complet"]]
    du = sum(a.get("cotisation") or 0 for a in actives)
    paye = sum(min(a.get("montant_paye") or 0, a.get("cotisation") or a.get("montant_paye") or 0) for a in actives)
    res = {"effectif": len(actives), "categories": dict(sorted(cats.items(), key=lambda x: cat.ORDRE.get(x[0], 99))),
           "sexes": dict(sexes), "licences": dict(licences), "incomplets": len(incomplets),
           "cotisations_dues": round(du, 2), "cotisations_payees": round(paye, 2), "reste": round(max(0, du - paye), 2),
           "mineurs": sum(1 for a in actives if a.get("mineur")), "annulees": len(adhesions) - len(actives)}
    if precedentes is not None:
        avant = {a["personne_id"] for a in precedentes if a.get("statut") != "annulee"}
        maintenant = {a["personne_id"] for a in actives}
        res["renouveles"] = len(avant & maintenant)
        res["nouveaux"] = len(maintenant - avant)
        res["non_renouveles"] = sorted(avant - maintenant)
        res["taux_renouvellement"] = round(100 * len(avant & maintenant) / len(avant)) if avant else None
    return res


def alertes(adhesions, chiffres_saison, saison):
    """Liste de phrases à afficher en tête du tableau de bord du club."""
    res = []
    incomplets = [a for a in adhesions if a.get("statut") != "annulee" and not dossier(a, saison)["complet"]]
    if incomplets:
        res.append(f"{len(incomplets)} dossier{'s' if len(incomplets) > 1 else ''} incomplet"
                   f"{'s' if len(incomplets) > 1 else ''} pour {saison}.")
    sans_ap = [a for a in adhesions if a.get("mineur") and not a.get("autorisation_parentale")
               and a.get("statut") != "annulee"]
    if sans_ap:
        res.append(f"{len(sans_ap)} mineur{'s' if len(sans_ap) > 1 else ''} sans autorisation parentale.")
    if chiffres_saison.get("reste"):
        res.append(f"{_fr(chiffres_saison['reste'])} € de cotisations restent à encaisser.")
    nr = chiffres_saison.get("non_renouveles") or []
    if nr:
        res.append(f"{len(nr)} adhérent{'s' if len(nr) > 1 else ''} de la saison précédente "
                   f"n'{'ont' if len(nr) > 1 else 'a'} pas encore renouvelé.")
    return res


def tarif_pour(tarifs, type_licence, categorie_code=None):
    """Le tarif de la saison qui correspond le mieux : même type de licence, sinon le tarif général
    (sans type). tarifs : [{libelle, type_licence, montant}]."""
    pareil = [t for t in tarifs if t.get("type_licence") == type_licence]
    if pareil:
        return pareil[0]
    general = [t for t in tarifs if not t.get("type_licence")]
    return general[0] if general else None
