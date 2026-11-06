"""
Accès aux données du chrono (étape 4.5) : départ réel de chaque épreuve,
passages d'arrivée (saisis au « top », importés d'un fichier), statuts de
course, classements, export, publication des résultats sur les profils des
licenciés (une fois seulement, même si l'on publie à nouveau).
"""

import csv
import io
from datetime import datetime

from noyau.donnees import base, organisation as dor, personnes as dper, profils as dpro
from noyau.organisation import chrono as C

ErreurChrono = C.ErreurChrono


def donner_depart(epreuve_id, heure_iso=None):
    """Enregistre le départ réel (maintenant par défaut) ; renvoie l'heure enregistrée."""
    h = heure_iso or datetime.now().isoformat(timespec="milliseconds")
    datetime.fromisoformat(h)
    base.ecrire("UPDATE epreuves SET depart_reel=? WHERE id=?", (h, epreuve_id))
    return h


def annuler_depart(epreuve_id):
    base.ecrire("UPDATE epreuves SET depart_reel=NULL WHERE id=?", (epreuve_id,))


def passages(evenement_id, avec_annules=False):
    cles = ("id", "dossard", "heure", "point", "source", "annule")
    sql = "SELECT id, dossard, heure, point, source, annule FROM chrono_passages WHERE evenement_id=?"
    if not avec_annules:
        sql += " AND annule=0"
    return [dict(zip(cles, l)) for l in base.lire_tous(sql + " ORDER BY heure, id", (evenement_id,))]


def _dossards(evenement_id):
    return {i["dossard"]: i for i in dor.inscriptions(evenement_id) if i.get("dossard") and i["statut"] != "annulee"}


def ajouter_passage(evenement_id, dossard, heure_iso=None, source="saisie", point="arrivee"):
    """Un passage à l'arrivée (ou à un point de contrôle : point « pc12 », étape 6). Renvoie {id, heure, inscrit
    (ou None), avertissement}."""
    h = heure_iso or datetime.now().isoformat(timespec="milliseconds")
    d = int(dossard) if dossard not in (None, "") else None
    pid = base.inserer("chrono_passages", {"evenement_id": evenement_id, "dossard": d, "heure": h, "source": source,
                                           "point": point or "arrivee"})
    ins = _dossards(evenement_id).get(d) if d else None
    avert = None
    if d and not ins:
        avert = f"dossard {d} inconnu"
    elif d:
        avant = [p for p in passages(evenement_id) if p["dossard"] == d and p["id"] != pid and p["point"] == (point or "arrivee")]
        if avant:
            ecart = abs(C.secondes_entre(avant[-1]["heure"], h))
            if ecart <= C.DOUBLON_SECONDES:
                base.ecrire("UPDATE chrono_passages SET annule=1 WHERE id=?", (pid,))
                avert = f"dossard {d} déjà pointé il y a {ecart:.0f} s : double top ignoré"
            else:
                avert = (f"dossard {d} déjà arrivé : passage gardé de côté (doublon)" if (point or "arrivee") == "arrivee"
                         else f"dossard {d} déjà pointé ici : passage gardé de côté (doublon)")
    return {"id": pid, "heure": h, "inscrit": ins, "avertissement": avert}


def corriger_passage(passage_id, dossard=None, heure_iso=None):
    v = {}
    if dossard is not None:
        v["dossard"] = int(dossard) if dossard != "" else None
    if heure_iso:
        datetime.fromisoformat(heure_iso)
        v["heure"] = heure_iso
    if v:
        base.ecrire(f"UPDATE chrono_passages SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (passage_id,))


def annuler_passage(passage_id, annule=True):
    base.ecrire("UPDATE chrono_passages SET annule=? WHERE id=?", (1 if annule else 0, passage_id))


def importer_fichier(evenement_id, lus, source="fichier"):
    """Passages lus par noyau/organisation/chrono.lire_fichier : heures ajoutées comme passages, temps de course
    posés sur l'inscription. Renvoie {passages, temps, inconnus}."""
    ins = _dossards(evenement_id)
    n_p = n_t = 0
    inconnus = []
    deja = {(p["dossard"], p["heure"]) for p in passages(evenement_id, True)}
    for l in lus:
        if l["dossard"] not in ins:
            inconnus.append(l["dossard"])
        if "heure" in l:
            if (l["dossard"], l["heure"]) not in deja:
                base.inserer("chrono_passages", {"evenement_id": evenement_id, "dossard": l["dossard"], "heure": l["heure"],
                                                 "source": source})
                deja.add((l["dossard"], l["heure"]))
                n_p += 1
        elif l["dossard"] in ins:
            base.ecrire("UPDATE inscriptions SET temps_corrige_s=? WHERE id=?", (l["temps_s"], ins[l["dossard"]]["id"]))
            n_t += 1
    return {"passages": n_p, "temps": n_t, "inconnus": sorted(set(inconnus))}


def definir_statut(inscription_ids, statut=None):
    """Abandon, disqualifié, non partant ; None remet en course."""
    if statut and statut not in C.LIBELLE_STATUT_COURSE:
        raise ErreurChrono("Statut inconnu.")
    for i in inscription_ids:
        base.ecrire("UPDATE inscriptions SET statut_course=? WHERE id=?", (statut if statut != "classe" else None, i))


def corriger_temps(inscription_id, temps_s):
    base.ecrire("UPDATE inscriptions SET temps_corrige_s=? WHERE id=?", (temps_s, inscription_id))


def _avec_chrono(evenement_id):
    """Inscriptions validées avec statut_course et temps_corrige_s."""
    extra = {r[0]: (r[1], r[2]) for r in base.lire_tous(
        "SELECT i.id, i.statut_course, i.temps_corrige_s FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id "
        "WHERE p.evenement_id=?", (evenement_id,))}
    res = []
    for i in dor.inscriptions(evenement_id):
        if i["statut"] in ("annulee", "liste_attente"):
            continue
        i["statut_course"], i["temps_corrige_s"] = extra.get(i["id"], (None, None))
        res.append(i)
    return res


def etat(evenement_id):
    """Contrôle du chrono : par épreuve {epreuve, depart, partants, arrives, en_course, abandons} ; passages
    doublons, dossards inconnus, passages sans dossard."""
    ins = _avec_chrono(evenement_id)
    ctl = C.controler_passages([p for p in passages(evenement_id) if p["point"] == "arrivee"],
                               {i["dossard"] for i in ins if i.get("dossard")})
    par = []
    for e in dor.epreuves(evenement_id):
        lot = [i for i in ins if i["epreuve_id"] == e["id"] and i.get("dossard")]
        arr = sum(1 for i in lot if i["dossard"] in ctl["retenus"] or i.get("temps_corrige_s"))
        hors = sum(1 for i in lot if i.get("statut_course") in ("abandon", "disqualifie", "non_partant"))
        par.append({"epreuve_id": e["id"], "epreuve": e["nom"], "depart": e.get("depart_reel"),
                    "heure_prevue": e.get("heure_depart"), "partants": len(lot), "arrives": arr,
                    "hors_course": hors, "en_course": max(0, len(lot) - arr - hors)})
    return {"epreuves": par, "doublons": ctl["doublons"], "inconnus": ctl["inconnus"], "sans_dossard": ctl["sans_dossard"]}


def classement(evenement_id, epreuve_id):
    ev = dor.evenement(evenement_id)
    e = next((x for x in dor.epreuves(evenement_id) if x["id"] == epreuve_id), None)
    if not e:
        return []
    ins = [i for i in _avec_chrono(evenement_id) if i["epreuve_id"] == epreuve_id]
    ctl = C.controler_passages([p for p in passages(evenement_id) if p["point"] == "arrivee"],
                               {i["dossard"] for i in ins if i.get("dossard")})
    return C.classement(e, ins, ctl["retenus"], e.get("date") or ev["date_debut"])


def export_csv(lignes, epreuve_nom=""):
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Clt", "Dossard", "Nom", "Prénom", "Sexe", "Catégorie", "Clt sexe", "Clt cat.", "Club", "Temps", "Écart",
                "Vitesse (km/h)", "Allure", "Épreuve"])
    for l in lignes:
        w.writerow([l.get("rang") or "", l.get("dossard") or "", l["nom"], l.get("prenom") or "", l.get("sexe") or "",
                    l["categorie"], l.get("rang_sexe") or "", l.get("rang_categorie") or "", l.get("club") or "",
                    l["temps"], l.get("ecart") or "", str(l["vitesse"]).replace(".", ",") if l.get("vitesse") else "",
                    l.get("allure") or "", epreuve_nom])
    return "﻿" + out.getvalue()


def publier_sur_profils(evenement_id):
    """Résultats de chaque épreuve sur le profil des participants retrouvés dans Trail Hub (fiche Personne liée à
    l'inscription, ou même nom, prénom et naissance). Clé unique par inscription : publier à nouveau met à jour.
    Renvoie {publies, mis_a_jour, sans_profil}."""
    ev = dor.evenement(evenement_id)
    pub = maj = sans = 0
    for e in dor.epreuves(evenement_id):
        lignes = classement(evenement_id, e["id"])
        nb = sum(1 for l in lignes if l["statut"] == "classe")
        for l in lignes:
            pid = l.get("personne_id")
            if not pid and l.get("date_naissance"):
                d = dper.doublons_possibles(l["nom"], l.get("prenom") or "", l["date_naissance"])
                pid = d[0]["id"] if len(d) == 1 and d[0]["date_naissance"] else None
                if pid:
                    base.ecrire("UPDATE inscriptions SET personne_id=? WHERE id=?", (pid, l["id"]))
            if not pid:
                sans += 1
                continue
            _rid, cree = dpro.enregistrer_resultat(pid, {
                "date": e.get("date") or ev["date_debut"], "course": ev["nom"], "epreuve": e["nom"], "commune": ev.get("commune"),
                "distance_km": e.get("distance_km"), "denivele_m": e.get("denivele_m"), "temps_s": l.get("temps_s"),
                "statut": l["statut"], "classement_general": l.get("rang"), "nb_classes": nb,
                "classement_sexe": l.get("rang_sexe"), "classement_categorie": l.get("rang_categorie"),
                "categorie": l["categorie"], "source": "Chrono du club", "evenement_id": evenement_id,
                "inscription_id": l["id"]}, cle=f"ev{evenement_id}|ins{l['id']}")
            pub += cree
            maj += not cree
    return {"publies": pub, "mis_a_jour": maj, "sans_profil": sans}
