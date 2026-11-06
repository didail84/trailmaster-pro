"""
Mise en service et recette (étape 8), sans Qt.

- Contrôles automatiques : ce que le logiciel peut vérifier tout seul sur
  cet ordinateur (base à jour, sauvegarde récente, modules, club, course,
  serveur, lecture des dossards, trousseau, envoi d'e-mails, Relais).
- Recette : la liste des essais à faire pour de vrai, étape par étape du
  Master Plan (« fini quand »), que tu coches au fur et à mesure avec une
  note. C'est elle qui dit quand une étape est vraiment terminée.
- Répétition générale : une course fictive complète (épreuves, coureurs
  inventés, dossards, points de contrôle, postes) pour s'entraîner avec les
  bénévoles et les téléphones avant le vrai jour, puis supprimée d'un clic.
"""

from datetime import date, datetime, timedelta

from noyau.donnees import base

ETATS = (("a_faire", "À faire"), ("fait", "Fait, ça marche"), ("probleme", "Problème trouvé"), ("sans_objet", "Sans objet"))
LIBELLE_ETAT = dict(ETATS)

RECETTE = (
    # (code, étape, essai à faire pour de vrai)
    ("e1_base", "1-2 · Noyau", "Ouvrir ta vraie base : sorties, forme, plans et Réglages comme avant"),
    ("e2_passeport", "1-2 · Noyau", "Exporter ton passeport coureur, le réimporter sur un autre ordinateur"),
    ("e2_sauvegarde", "1-2 · Noyau", "Faire une sauvegarde, puis la restaurer sur un autre ordinateur"),
    ("e3_roadbook", "3 · Stratégie", "Préparer une vraie course du calendrier : roadbook, nutrition, matériel obligatoire"),
    ("e3_apres", "3 · Stratégie", "Après la course : saisir le résultat, regarder Analyse > Prévu ou réel"),
    ("e4_adherents", "4 · Club", "Importer les vrais adhérents (HelloAsso ou SI-FFA) dans la bonne association"),
    ("e4_saison", "4 · Club", "Un mois d'appels aux entraînements, reçus de cotisation imprimés"),
    ("e4_course", "4 · Organisation", "Une course : inscriptions importées, dossiers contrôlés, dossards, démarches, bénévoles"),
    ("e4_chrono", "4 · Organisation", "Chrono et classements publiés sur les profils des licenciés"),
    ("e5_nas", "5 · Serveur", "Serveur installé sur le NAS (LISEZ-MOI), compte administrateur créé"),
    ("e5_postes", "5 · Serveur", "Deux postes du bureau branchés, qui modifient en même temps"),
    ("e5_telephones", "5 · Serveur", "Téléphones (dont le vieil iPhone) : chrono, appel, mon poste"),
    ("e5_sauvegarde_nas", "5 · Serveur", "Sauvegarde du NAS vers le second NAS, et restauration essayée"),
    ("e6_repetition", "6 · Jour de course", "Répétition générale avec les bénévoles (course fictive, téléphones)"),
    ("e6_reel", "6 · Jour de course", "Une vraie course du club : PC course, incidents, Trail Live"),
    ("kids", "7 · Kids", "École d'athlé : carnets ouverts, parents connectés sur leur téléphone"),
    ("analyse", "7 · Analyse", "Une saison complète de données : bilans du club et des événements relus"),
    ("photos", "7 · Photos", "Photos d'une vraie course : part des dossards bien lus, photos rendues aux coureurs"),
    ("e8_mac", "8 · Installations", "Mac sous macOS 12 : installé par le .dmg, lecture des dossards essayée"),
    ("e8_windows", "8 · Installations", "Windows : installé par l'installateur, puis par la version portable"),
    ("e8_linux", "8 · Installations", "Linux : AppImage ou .deb, trousseau de mots de passe"),
    ("e8_relais", "8 · Installations", "Une mise à jour reçue par Relais (NAS ou GitHub) sur chaque ordinateur"),
    ("e8_rgpd", "8 · Données personnelles", "Registre des traitements relu, consentements recueillis, durées fixées"),
)
ETAPES = list(dict.fromkeys(e for _c, e, _l in RECETTE))


def recette():
    faits = {r[0]: r for r in base.lire_tous("SELECT code, etat, note, par, maj FROM recette")}
    res = []
    for code, etape, libelle in RECETTE:
        r = faits.get(code)
        res.append({"code": code, "etape": etape, "libelle": libelle, "etat": r[1] if r else "a_faire",
                    "note": r[2] if r else None, "par": r[3] if r else None, "maj": r[4] if r else None})
    return res


def noter(code, etat, note=None, par=None):
    if code not in {c for c, _e, _l in RECETTE}:
        raise ValueError("Essai inconnu.")
    if etat not in LIBELLE_ETAT:
        raise ValueError("État inconnu.")
    base.ecrire("INSERT INTO recette (code, etat, note, par, maj) VALUES (?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET "
                "etat=excluded.etat, note=excluded.note, par=excluded.par, maj=excluded.maj",
                (code, etat, (note or "").strip() or None, par, datetime.now().isoformat(timespec="minutes")))


def avancement():
    """{étape: {total, faits, problemes}} et le total général (sans objet exclu)."""
    res = {}
    for r in recette():
        e = res.setdefault(r["etape"], {"total": 0, "faits": 0, "problemes": 0})
        if r["etat"] == "sans_objet":
            continue
        e["total"] += 1
        e["faits"] += r["etat"] == "fait"
        e["problemes"] += r["etat"] == "probleme"
    t = {"total": sum(x["total"] for x in res.values()), "faits": sum(x["faits"] for x in res.values()),
         "problemes": sum(x["problemes"] for x in res.values())}
    return res, t


# ------------------------------------------------------------------ contrôles automatiques

def _par(cle):
    l = base.lire_un("SELECT valeur FROM parametres_app WHERE cle=?", (cle,))
    return l[0] if l else None


def _c(code, libelle, etat, detail):
    return {"code": code, "libelle": libelle, "etat": etat, "detail": detail}


def controles(reseau=False, aujourdhui=None):
    """Liste de {code, libellé, état (ok, attention, echec, info), détail}. reseau=True essaie aussi le serveur et
    Relais (quelques secondes)."""
    import data.database as db
    import data.migrations as mig
    j = aujourdhui or date.today()
    res = []
    v = base.lire_un("SELECT MAX(version) FROM schema_version")[0] or 0
    res.append(_c("base", "Base de données", "ok" if v == mig.VERSION_LOGICIEL else "echec",
                  f"version {v} sur {mig.VERSION_LOGICIEL} · {db.CHEMIN_BDD}"))
    s = _par("derniere_sauvegarde")
    if not s:
        res.append(_c("sauvegarde", "Sauvegarde", "attention", "aucune sauvegarde faite depuis Réglages"))
    else:
        jours = (j - date.fromisoformat(s[:10])).days
        res.append(_c("sauvegarde", "Sauvegarde", "ok" if jours <= 7 else "attention",
                      f"dernière il y a {jours} jour(s) ({s[:10]})"))
    from noyau import modules as MO
    actifs = [m.nom for m in MO.MODULES if MO.est_actif(m.code)]
    res.append(_c("modules", "Modules allumés", "info", ", ".join(actifs)))
    try:
        n_clubs = base.lire_un("SELECT COUNT(*) FROM clubs")[0]
        from noyau.club import categories as cat
        n_adh = base.lire_un("SELECT COUNT(*) FROM adhesions WHERE saison=? AND statut != 'annulee'", (cat.saison_de(j),))[0]
        res.append(_c("club", "Club", "ok" if n_adh else ("attention" if n_clubs else "info"),
                      f"{n_clubs} association(s), {n_adh} adhérent(s) en {cat.saison_de(j)}" if n_clubs
                      else "pas encore d'association"))
    except Exception:
        pass
    try:
        ev = base.lire_un("SELECT id, nom, date_debut FROM evenements WHERE date_debut >= ? AND COALESCE(notes, '') NOT LIKE "
                          "'%[répétition]%' ORDER BY date_debut LIMIT 1", (j.isoformat(),))
        if ev:
            sans_plage = base.lire_un("SELECT COUNT(*) FROM epreuves WHERE evenement_id=? AND (dossard_debut IS NULL OR "
                                      "dossard_fin IS NULL)", (ev[0],))[0]
            n_ins = base.lire_un("SELECT COUNT(*) FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id WHERE "
                                 "p.evenement_id=? AND i.statut != 'annulee'", (ev[0],))[0]
            image = base.lire_un("SELECT COUNT(*) FROM inscriptions i JOIN epreuves p ON p.id = i.epreuve_id WHERE "
                                 "p.evenement_id=? AND i.statut != 'annulee' AND i.droit_image = 1", (ev[0],))[0]
            res.append(_c("course", "Prochaine course", "attention" if sans_plage else "ok",
                          f"{ev[1]} le {ev[2]} · {n_ins} inscrit(s), {image} accord(s) pour l'image"
                          + (f" · {sans_plage} épreuve(s) sans plage de dossards" if sans_plage else "")))
        else:
            res.append(_c("course", "Prochaine course", "info", "pas de course à venir dans l'Organisation"))
    except Exception:
        pass
    from noyau.photos import lecture
    res.append(_c("dossards", "Lecture automatique des dossards", "ok" if lecture.disponible() else "attention",
                  "installée sur cet ordinateur" if lecture.disponible() else
                  "pas installée : pip install rapidocr_onnxruntime (sinon saisie à la main)"))
    try:
        import keyring
        k = keyring.get_keyring()
        nom = type(k).__name__
        ok = "fail" not in type(k).__module__ and "Null" not in nom
        res.append(_c("trousseau", "Trousseau des mots de passe", "ok" if ok else "attention",
                      nom if ok else "aucun trousseau : connexion au serveur et e-mails à retaper à chaque fois"))
    except Exception as e:
        res.append(_c("trousseau", "Trousseau des mots de passe", "attention", str(e)[:120]))
    smtp = _par("smtp_hote")
    res.append(_c("courriel", "Envoi d'e-mails (photos)", "ok" if smtp else "info", smtp or "pas encore réglé"))
    from noyau.relais import manifeste as RM
    res.append(_c("relais", "Mises à jour (Relais)", "ok" if RM.cle_publique() else "attention",
                  ("signées" if RM.cle_publique() else "clé de signature pas encore créée (packaging/relais_manifeste.py "
                                                       "--creer-cles)") + f" · canal {_par('relais_canal') or 'stable'}"
                  + (f" · NAS {_par('relais_url')}" if _par("relais_url") else "")))
    url = _par("serveur_url")
    if not url:
        res.append(_c("serveur", "Serveur du club", "info", "ce poste travaille en local"))
    elif reseau:
        try:
            from noyau.serveur import client as C
            i = C.Client(url, empreinte=_par("serveur_empreinte") or None).info()
            res.append(_c("serveur", "Serveur du club", "ok" if i.get("base") == mig.VERSION_LOGICIEL else "attention",
                          f"{url} joignable · base du serveur en version {i.get('base')}"))
        except Exception as e:
            res.append(_c("serveur", "Serveur du club", "echec", f"{url} injoignable : {str(e)[:120]}"))
    else:
        res.append(_c("serveur", "Serveur du club", "info", f"{url} (clique « Vérifier le réseau » pour l'essayer)"))
    if reseau:
        try:
            from noyau.relais import client as RC
            canal, nas = RC.reglages()
            r = RC.chercher(RC.version_installee(), canal, nas)
            res.append(_c("relais_reseau", "Relais joignable", "ok" if r else "attention",
                          (f"{r['source']} : version {r['version']}" + (" (à jour)" if r["a_jour"] else " disponible"))
                          if r else "aucun manifeste trouvé (versions publiées avant Relais, ou hors ligne)"))
        except Exception as e:
            res.append(_c("relais_reseau", "Relais joignable", "echec", str(e)[:150]))
    return res


# ------------------------------------------------------------------ répétition générale

MARQUE = "[répétition]"


def repetition():
    l = base.lire_un("SELECT id FROM evenements WHERE notes LIKE ?", (f"%{MARQUE}%",))
    return l[0] if l else None


def creer_repetition(jour=None, coureurs=40):
    """Une course fictive pour s'entraîner : 2 épreuves, des coureurs inventés (« Coureur 01 »…), dossards, points
    de contrôle et postes de bénévoles. Renvoie l'id de l'événement (le même si elle existe déjà)."""
    deja = repetition()
    if deja:
        return deja
    from noyau.donnees import organisation as dor, commandement as dk, logistique as dlo
    j = (jour or date.today() + timedelta(days=1)).isoformat()
    ev = dor.enregistrer_evenement({"nom": "Répétition générale (course fictive)", "date_debut": j, "commune": "Exemple",
                                    "notes": f"{MARQUE} Course d'entraînement : à supprimer dans Mise en service."})
    e1 = dor.enregistrer_epreuve(ev, {"nom": "Trail 12 km", "distance_km": 12, "denivele_m": 450, "heure_depart": "09:00",
                                      "dossard_debut": 1, "dossard_fin": 299, "tarif": 0})
    e2 = dor.enregistrer_epreuve(ev, {"nom": "Trail 25 km", "distance_km": 25, "denivele_m": 1100, "heure_depart": "08:30",
                                      "dossard_debut": 300, "dossard_fin": 599, "tarif": 0})
    for k in range(1, coureurs + 1):
        dor.enregistrer_inscription({"epreuve_id": e1 if k % 3 else e2, "nom": f"COUREUR {k:02d}", "prenom": "Essai",
                                     "sexe": "F" if k % 2 else "M", "date_naissance": f"{1965 + k % 35}-05-01",
                                     "statut": "validee", "justificatif": "pps", "justificatif_valide": 1,
                                     "droit_image": 1, "source": "repetition"})
    dor.attribuer_dossards(ev)
    for nom, km in (("Ravito du col", 6.0), ("Croisement de la piste", 9.5)):
        dk.enregistrer_point(ev, {"nom": nom, "km": km})
    for nom in ("Départ et arrivée", "Ravito du col", "Serre-file"):
        dlo.enregistrer_poste(ev, {"nom": nom, "heure_debut": "07:30", "heure_fin": "13:00", "besoin": 2})
    return ev


def supprimer_repetition():
    ev = repetition()
    if not ev:
        return False
    from noyau.donnees import organisation as dor
    dor.supprimer_evenement(ev)
    return True


def rapport():
    """Données du rapport de mise en service (PDF) : contrôles et recette."""
    av, t = avancement()
    return {"date": date.today().isoformat(), "controles": controles(), "recette": recette(), "avancement": av, "total": t}
