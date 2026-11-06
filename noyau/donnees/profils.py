"""
Accès aux données des profils de licenciés (étape 4.3) : résultats (saisis,
importés d'un classement extérieur ou venus du chrono du club), index,
records, présences, diplômes des entraîneurs, bibliothèque de séances du
club partagées aux groupes et envoyées dans la planification des coureurs.

Un licencié qui a aussi un profil coureur dans Trail Hub retrouve ses
résultats dans « Résultats de courses » : un seul enregistrement par course,
jamais de doublon.
"""

import json
from datetime import date, timedelta

from noyau.donnees import base, club as dclub, personnes as dper, agenda_club as dag
from noyau.club import profils as P, categories as cat
from noyau.club import agenda as ag

ErreurProfil = P.ErreurProfil
CHAMPS_RESULTAT = ("date", "course", "epreuve", "commune", "discipline", "distance_km", "denivele_m", "temps_s", "statut",
                   "classement_general", "nb_classes", "classement_sexe", "classement_categorie", "categorie", "source",
                   "evenement_id", "inscription_id", "notes")


# ------------------------------------------------------------------ résultats

def resultats(personne_id):
    cles = ("id", "cle") + CHAMPS_RESULTAT + ("resultat_course_id",)
    return [dict(zip(cles, l)) for l in base.lire_tous(
        f"SELECT id, cle, {', '.join(CHAMPS_RESULTAT)}, resultat_course_id FROM resultats_licencies WHERE personne_id=? "
        "ORDER BY date DESC, id DESC", (personne_id,))]


def resultats_du_club(club_id, debut=None, fin=None):
    """Résultats des adhérents du club sur la période, avec le nom : le plus récent d'abord."""
    sql = ("SELECT r.id, r.personne_id, p.nom, p.prenom, r.date, r.course, r.epreuve, r.distance_km, r.denivele_m, "
           "r.temps_s, r.statut, r.classement_general, r.nb_classes, r.classement_sexe, r.classement_categorie, "
           "r.categorie, r.source FROM resultats_licencies r JOIN personnes p ON p.id = r.personne_id "
           "WHERE r.personne_id IN (SELECT personne_id FROM adhesions WHERE club_id=?)")
    par = [club_id]
    if debut:
        sql += " AND r.date >= ?"
        par.append(str(debut)[:10])
    if fin:
        sql += " AND r.date <= ?"
        par.append(str(fin)[:10])
    cles = ("id", "personne_id", "nom", "prenom", "date", "course", "epreuve", "distance_km", "denivele_m", "temps_s",
            "statut", "classement_general", "nb_classes", "classement_sexe", "classement_categorie", "categorie", "source")
    return [dict(zip(cles, l)) for l in base.lire_tous(sql + " ORDER BY r.date DESC, p.nom", tuple(par))]


def _verifier(v):
    if not (v.get("course") or "").strip():
        raise ErreurProfil("Donne le nom de la course.")
    if not v.get("date"):
        raise ErreurProfil("Donne la date de la course.")
    v["course"] = v["course"].strip()
    v["date"] = str(v["date"])[:10]
    if v.get("statut") and v["statut"] not in P.LIBELLE_STATUT_RESULTAT:
        raise ErreurProfil("Statut inconnu.")
    v["statut"] = v.get("statut") or ("classe" if v.get("temps_s") else "classe")
    if isinstance(v.get("temps_s"), str):
        v["temps_s"] = P.lire_temps(v["temps_s"])
    if v.get("distance_km") is not None and float(v["distance_km"]) < 0:
        raise ErreurProfil("La distance ne peut pas être négative.")
    if not v.get("discipline"):
        v["discipline"] = P.discipline_de(v)
    return v


def enregistrer_resultat(personne_id, champs, resultat_id=None, cle=None):
    """Ajoute ou met à jour un résultat. `cle` identifie la course pour éviter les doublons (sinon calculée
    depuis la date, la course, l'épreuve et la distance) ; une même clé met à jour au lieu d'ajouter.
    Renvoie (id, créé ?)."""
    v = _verifier({k: champs.get(k) for k in CHAMPS_RESULTAT if k in champs})
    if resultat_id is None:
        cle = cle or P.cle_resultat(personne_id, v["date"], v["course"], v.get("epreuve"), v.get("distance_km"))
        l = base.lire_un("SELECT id FROM resultats_licencies WHERE cle=?", (cle,))
        if l:
            resultat_id, cree = l[0], False
            base.ecrire(f"UPDATE resultats_licencies SET {', '.join(k + '=?' for k in v)} WHERE id=?",
                        tuple(v.values()) + (resultat_id,))
        else:
            resultat_id, cree = base.inserer("resultats_licencies", {"personne_id": personne_id, "cle": cle, **v}), True
    else:
        cree = False
        base.ecrire(f"UPDATE resultats_licencies SET {', '.join(k + '=?' for k in v)} WHERE id=?",
                    tuple(v.values()) + (resultat_id,))
    _vers_resultats_coureur(personne_id, resultat_id)
    return resultat_id, cree


def _vers_resultats_coureur(personne_id, resultat_id):
    """Recopie le résultat dans « Résultats de courses » si le licencié a un profil coureur (une seule fois)."""
    athlete_id = dper.athlete_de_la_personne(personne_id)
    if not athlete_id:
        return
    r = next((x for x in resultats(personne_id) if x["id"] == resultat_id), None)
    if not r:
        return
    nom = r["course"] + (f" — {r['epreuve']}" if r.get("epreuve") and r["epreuve"] not in r["course"] else "")
    v = {"athlete_id": athlete_id, "nom_course": nom, "date": r["date"], "distance": r.get("distance_km"),
         "denivele": r.get("denivele_m"), "temps": P.texte_temps(r["temps_s"]) if r.get("temps_s") else
         P.LIBELLE_STATUT_RESULTAT.get(r["statut"]), "classement_general": r.get("classement_general"),
         "classement_categorie": r.get("classement_categorie")}
    existant = r.get("resultat_course_id") and base.lire_un("SELECT id FROM resultats_courses WHERE id=?",
                                                           (r["resultat_course_id"],))
    if not existant:
        l = base.lire_un("SELECT id FROM resultats_courses WHERE athlete_id=? AND date=? AND nom_course=?",
                         (athlete_id, r["date"], nom))
        existant = l
    if existant:
        rid = existant[0]
        base.ecrire("UPDATE resultats_courses SET distance=?, denivele=?, temps=?, classement_general=?, "
                    "classement_categorie=? WHERE id=?", (v["distance"], v["denivele"], v["temps"],
                                                          v["classement_general"], v["classement_categorie"], rid))
    else:
        rid = base.inserer("resultats_courses", v)
    base.ecrire("UPDATE resultats_licencies SET resultat_course_id=? WHERE id=?", (rid, resultat_id))


def supprimer_resultat(resultat_id):
    base.ecrire("DELETE FROM resultats_licencies WHERE id=?", (resultat_id,))


def importer_classement(club_id, saison, course, lignes, nb_classes=None):
    """Résultats d'une course extérieure pour les adhérents retrouvés dans le classement.
    course : {course, date, epreuve, distance_km, denivele_m, commune}. Renvoie {associes, ajoutes,
    mis_a_jour, non_trouves: [noms du club non retrouvés]}."""
    adh = [a for a in dclub.adhesions(club_id, saison) if a["statut"] != "annulee"]
    paires = P.associer(lignes, adh)
    nb = nb_classes or sum(1 for l in lignes if l["statut"] == "classe")
    ajout = maj = 0
    for l, a in paires:
        _rid, cree = enregistrer_resultat(a["personne_id"], {
            **course, "temps_s": l["temps_s"], "statut": l["statut"], "classement_general": l["rang"],
            "nb_classes": nb, "classement_sexe": l.get("rang_sexe"), "classement_categorie": l.get("rang_categorie"),
            "categorie": l.get("categorie"), "source": "Classement importé"})
        ajout += cree
        maj += not cree
    club = (dclub.club_principal() or {}).get("nom") or ""
    vus = {id(l) for l, _a in paires}
    non = [f"{l['prenom']} {l['nom']}" for l in lignes if id(l) not in vus and club and l.get("club")
           and imp_cle(club) and imp_cle(club) in imp_cle(l["club"])]
    return {"associes": len(paires), "ajoutes": ajout, "mis_a_jour": maj, "non_trouves": non}


def imp_cle(t):
    from noyau.club.imports import _cle
    return _cle(t)


# ------------------------------------------------------------------ profil complet

def profil(personne_id, club_id=None, saison=None):
    saison = saison or cat.saison_de()
    f = dper.fiche(personne_id)
    if not f:
        return None
    rs = resultats(personne_id)
    adh = next((a for a in dclub.adhesions_de_la_personne(personne_id) if a["saison"] == saison), None)
    d0, d1 = cat.bornes_saison(saison)
    auj = date.today()
    assid = dag.assiduite(club_id, d0, min(d1, auj)) if club_id else {}
    return {"fiche": f, "adhesion": adh, "categorie": cat.categorie(f.get("date_naissance"), saison),
            "groupes": [g["nom"] for g in dclub.groupes(club_id) if g["id"] in set(dclub.groupes_de(personne_id))]
            if club_id else [], "index": dper.index_de(personne_id), "resultats": rs, "records": P.records(rs),
            "bilan_saison": P.bilan(rs, d0, d1), "bilan_total": P.bilan(rs), "presences": assid.get(personne_id),
            "diplomes": diplomes(personne_id), "athlete_id": dper.athlete_de_la_personne(personne_id),
            "saison": saison}


# ------------------------------------------------------------------ diplômes et entraîneurs

def diplomes(personne_id):
    cles = ("id", "intitule", "organisme", "date_obtention", "date_validite", "notes")
    res = [dict(zip(cles, l)) for l in base.lire_tous(
        "SELECT id, intitule, organisme, date_obtention, date_validite, notes FROM diplomes WHERE personne_id=? "
        "ORDER BY COALESCE(date_validite, '9999') ", (personne_id,))]
    for d in res:
        d["etat"] = P.etat_diplome(d)
    return res


def enregistrer_diplome(personne_id, champs, diplome_id=None):
    v = {k: (champs.get(k) or None) for k in ("intitule", "organisme", "date_obtention", "date_validite", "notes")}
    if not (v["intitule"] or "").strip():
        raise ErreurProfil("Donne l'intitulé du diplôme (ex. Entraîneur Running, Coach Athlé Santé, PSC1).")
    if v["date_obtention"] and v["date_validite"] and v["date_validite"] < v["date_obtention"]:
        raise ErreurProfil("La fin de validité est avant la date d'obtention.")
    if diplome_id is None:
        r = dper.roles(personne_id)
        if "entraineur" not in r:
            dper.definir_roles(personne_id, list(r) + ["entraineur"])
        return base.inserer("diplomes", {"personne_id": personne_id, **v})
    base.ecrire(f"UPDATE diplomes SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (diplome_id,))
    return diplome_id


def supprimer_diplome(diplome_id):
    base.ecrire("DELETE FROM diplomes WHERE id=?", (diplome_id,))


def entraineurs(club_id, jours=60, aujourdhui=None):
    """Les entraîneurs du club (rôle entraîneur, ou entraîneur d'un groupe ou d'une séance) : groupes encadrés,
    séances encadrées sur `jours`, prochaines séances, diplômes et alertes."""
    auj = aujourdhui or date.today()
    ids = {p["id"] for p in dper.lister("entraineur")}
    gs = dclub.groupes(club_id, avec_inactifs=True)
    ids |= {g["entraineur_id"] for g in gs if g["entraineur_id"]}
    passees = dag.seances(club_id, auj - timedelta(days=jours), auj, avec_annulees=False)
    futures = dag.seances(club_id, auj + timedelta(days=1), auj + timedelta(days=30), avec_annulees=False)
    ids |= {s["entraineur_id"] for s in passees + futures if s["entraineur_id"]}
    res = []
    for pid in ids:
        f = dper.fiche(pid)
        if not f:
            continue
        ds = diplomes(pid)
        res.append({"personne_id": pid, "nom": f["nom"], "prenom": f["prenom"], "email": f.get("email"),
                    "telephone": f.get("telephone"), "groupes": [g["nom"] for g in gs if g["entraineur_id"] == pid],
                    "seances_encadrees": sum(1 for s in passees if s["entraineur_id"] == pid),
                    "prochaines": [s for s in futures if s["entraineur_id"] == pid][:5], "diplomes": ds,
                    "alertes": [f"{d['intitule']} : {d['etat']}" for d in ds if d["etat"] in ("expiré", "bientôt")]})
    return sorted(res, key=lambda e: (e["nom"].lower(), e["prenom"].lower()))


# ------------------------------------------------------------------ séances partagées

CHAMPS_MODELE = ("titre", "type", "objectif", "public", "duree_min", "contenu", "fractionne_code", "auteur_id")


def modeles(club_id):
    cles = ("id",) + CHAMPS_MODELE + ("auteur", "fois")
    res = [dict(zip(cles, l)) for l in base.lire_tous(
        f"SELECT m.id, {', '.join('m.' + c for c in CHAMPS_MODELE)}, (SELECT p.prenom || ' ' || p.nom FROM personnes p "
        "WHERE p.id = m.auteur_id), (SELECT COUNT(*) FROM seances_club s WHERE s.modele_id = m.id) FROM seances_modeles m "
        "WHERE m.club_id=? ORDER BY m.titre COLLATE NOCASE", (club_id,))]
    return res


def modele(modele_id):
    l = base.lire_un("SELECT club_id FROM seances_modeles WHERE id=?", (modele_id,))
    return next((m for m in modeles(l[0]) if m["id"] == modele_id), None) if l else None


def texte_modele(m, vma=None):
    """Contenu à partager : le texte de l'entraîneur, et, pour un fractionné de la bibliothèque, les cibles."""
    morceaux = [m.get("contenu") or ""]
    if m.get("fractionne_code"):
        from noyau.entrainement import fractionne as fr
        s = fr.modele(m["fractionne_code"])
        if s:
            morceaux.append(f"Fractionné : {s['nom']} — {fr.resume(s)}")
            if vma:
                c = fr.cibles(s, vma)
                vus = []
                for l in c["lignes"]:
                    t = f"{l['libelle']} : {P.texte_temps(l['temps_s'])} ({l['allure']}, {l['pct_vma']} % VMA {vma:g})"
                    if t not in vus:
                        vus.append(t)
                morceaux.append("Cibles : " + " ; ".join(vus[:6]))
    return "\n".join(x for x in morceaux if x).strip()


def enregistrer_modele(club_id, champs, modele_id=None):
    v = {k: champs.get(k) for k in CHAMPS_MODELE if k in champs}
    if "titre" in v or modele_id is None:
        v["titre"] = (v.get("titre") or "").strip()
        if not v["titre"]:
            raise ErreurProfil("Donne un titre à la séance.")
    if v.get("type") and v["type"] not in ag.LIBELLE_TYPE:
        raise ErreurProfil("Type de séance inconnu.")
    if v.get("fractionne_code"):
        from noyau.entrainement import fractionne as fr
        if not fr.modele(v["fractionne_code"]):
            raise ErreurProfil("Séance de fractionné inconnue.")
    if modele_id is None:
        return base.inserer("seances_modeles", {"club_id": club_id, **v})
    base.ecrire(f"UPDATE seances_modeles SET {', '.join(k + '=?' for k in v)} WHERE id=?", tuple(v.values()) + (modele_id,))
    return modele_id


def supprimer_modele(modele_id):
    base.ecrire("UPDATE seances_club SET modele_id=NULL WHERE modele_id=?", (modele_id,))
    base.ecrire("DELETE FROM seances_modeles WHERE id=?", (modele_id,))


def planifier(modele_id, club_id, jour, groupe_id=None, heure_debut=None, heure_fin=None, lieu=None, entraineur_id=None,
              seance_id=None):
    """Met la séance du club au programme d'un groupe : dans une séance existante de l'agenda (seance_id) ou
    une nouvelle. Renvoie l'id de la séance de l'agenda."""
    m = modele(modele_id)
    if not m:
        raise ErreurProfil("Séance introuvable.")
    contenu = texte_modele(m)
    if seance_id:
        dag.enregistrer_seance(club_id, {"contenu": contenu, "titre": m["titre"]}, seance_id)
    else:
        seance_id = dag.enregistrer_seance(club_id, {"titre": m["titre"], "type": m["type"] or "entrainement",
                                                     "date": jour, "groupe_id": groupe_id, "heure_debut": heure_debut,
                                                     "heure_fin": heure_fin, "lieu": lieu, "contenu": contenu,
                                                     "entraineur_id": entraineur_id or m.get("auteur_id")})
    base.ecrire("UPDATE seances_club SET modele_id=? WHERE id=?", (modele_id, seance_id))
    return seance_id


def envoyer_aux_coureurs(seance_id):
    """Pour chaque membre attendu de la séance qui a un profil coureur dans Trail Hub : la séance arrive dans
    sa planification (séances structurées), avec les allures de sa VMA pour un fractionné. Pas de doublon.
    Renvoie le nombre de coureurs servis."""
    s = dag.seance(seance_id)
    if not s:
        raise ErreurProfil("Séance introuvable.")
    l = base.lire_un("SELECT modele_id FROM seances_club WHERE id=?", (seance_id,))
    m = modele(l[0]) if l and l[0] else None
    n = 0
    for pid in dag.attendus(seance_id):
        aid = dper.athlete_de_la_personne(pid)
        if not aid:
            continue
        if base.lire_un("SELECT 1 FROM seances_structurees WHERE athlete_id=? AND date_prevue=? AND nom=?",
                        (aid, s["date"], s["titre"])):
            continue
        vma = (base.lire_un("SELECT vma FROM athletes WHERE id=?", (aid,)) or [None])[0]
        etapes = []
        notes = s.get("contenu") or ""
        if m and m.get("fractionne_code"):
            from noyau.entrainement import fractionne as fr
            st = fr.modele(m["fractionne_code"])
            if st and vma:
                etapes = fr.etapes_montre(st, vma)
            notes = texte_modele(m, vma)
        base.inserer("seances_structurees", {"athlete_id": aid, "nom": s["titre"], "date_prevue": s["date"],
                                             "type_seance": "Fractionné" if etapes else "Club", "statut": "Prévue",
                                             "etapes_json": json.dumps(etapes, ensure_ascii=False) if etapes else None,
                                             "notes": f"Séance du club ({s.get('groupe') or 'tout le club'})\n{notes}".strip()})
        n += 1
    return n
