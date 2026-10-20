"""
Synchronisation automatique avec Garmin Connect (v99).

La montre envoie ses données à Garmin Connect par Bluetooth via le
téléphone ; ce module va ensuite les chercher sur Internet, avec le
compte Garmin de l'utilisateur, et les range dans la base TrailMaster :

  - les SORTIES : fichier .FIT d'origine (trace GPS, FC, dénivelé),
    importé par la même mécanique que l'import USB (donc mêmes règles
    anti-doublons : une sortie déjà connue n'est jamais recréée, et on
    ne complète que ce qui manque) ;
  - la SANTÉ de chaque jour : FC de repos, VFC (HRV) de nuit et son statut,
    sommeil (durée, phases, score), Body Battery, stress, SpO₂, via le
    même rangement que l'import de l'export Garmin (data/import_sante_garmin) ;
  - des données EN PLUS (table garmin_quotidien) : pas, calories, minutes
    d'intensité, respiration, disponibilité d'entraînement (Training
    Readiness), statut d'entraînement, VO₂max, poids.

Accès : il n'existe pas d'accès officiel gratuit pour un logiciel
personnel ; on utilise la bibliothèque « garminconnect », qui se connecte
comme le site web. Garmin peut la casser sans prévenir : l'import par
export de données et par USB restent disponibles.

Sécurité : le mot de passe n'est jamais écrit dans la base. Seuls des
jetons de connexion sont gardés (dossier ~/.trailmaster/garmin, droits
réservés à l'utilisateur) ; le mot de passe n'est conservé que dans le
trousseau du système (Windows / macOS) quand il est disponible.

Aucune fonction ici n'utilise de widget : tout peut tourner dans un fil
de travail ; la progression passe par un dictionnaire partagé `etat`.
"""

import os
import shutil
import tempfile
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from data.database import connexion, definir_parametre, obtenir_parametre

DOSSIER_JETONS = Path.home() / ".trailmaster" / "garmin"
SERVICE_TROUSSEAU = "TrailMaster Pro - Garmin Connect"
PAUSE_ENTRE_APPELS_S = 0.25
JOURS_DETAIL_RECENT = 90      # Training Readiness / statut / VO2max : seulement le récent


class ErreurGarmin(Exception):
    """Erreur dont le message est déjà lisible par l'utilisateur."""


class SessionExpiree(ErreurGarmin):
    pass


class LimiteAtteinte(ErreurGarmin):
    pass


# ------------------------------------------------------------------
# CONNEXION
# ------------------------------------------------------------------

def bibliotheque_disponible():
    try:
        import garminconnect  # noqa: F401
        return True
    except Exception:
        return False


def _traduire_erreur(e):
    """Exception de la bibliothèque / du réseau -> ErreurGarmin lisible."""
    nom = type(e).__name__.lower()
    texte = str(e).lower()
    if isinstance(e, ErreurGarmin):
        return e
    if "429" in texte or "toomanyrequests" in nom or "too many" in texte or "rate" in texte and "limit" in texte:
        return LimiteAtteinte(
            "Garmin demande de ralentir (trop de demandes). Réessaie dans une heure ; "
            "ce qui a déjà été récupéré est conservé."
        )
    if "authentication" in nom or "401" in texte or "unauthor" in texte or "credential" in texte \
            or "password" in texte or "username" in texte:
        return SessionExpiree(
            "Connexion refusée par Garmin : vérifie l'adresse e-mail et le mot de passe "
            "de ton compte Garmin Connect."
        )
    if "mfa" in texte or "verification" in texte or "vérification" in texte:
        return ErreurGarmin(
            "Garmin demande un code de vérification (double authentification). "
            "Cette version ne le gère pas : désactive-la dans ton compte Garmin ou "
            "utilise l'import par export de données."
        )
    if "connection" in nom or "timeout" in nom or "connection" in texte or "resolve" in texte \
            or "network" in texte or "timed out" in texte:
        return ErreurGarmin("Pas de connexion Internet (ou Garmin ne répond pas). Réessaie plus tard.")
    return ErreurGarmin(f"Garmin Connect a répondu par une erreur : {e}")


def _refuser_mfa():
    raise ErreurGarmin(
        "Garmin demande un code de vérification (double authentification). "
        "Cette version ne le gère pas : désactive-la dans ton compte Garmin ou "
        "utilise l'import par export de données."
    )


def _sauver_jetons(g):
    DOSSIER_JETONS.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DOSSIER_JETONS, 0o700)
    except OSError:
        pass
    chemin = str(DOSSIER_JETONS)
    try:
        g.client.dump(chemin)           # garminconnect >= 0.3
    except AttributeError:
        g.garth.dump(chemin)            # garminconnect 0.2.x
    for f in DOSSIER_JETONS.glob("*"):
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass


def _lire_mdp_trousseau(email):
    try:
        import keyring
        return keyring.get_password(SERVICE_TROUSSEAU, email)
    except Exception:
        return None


def _ecrire_mdp_trousseau(email, mdp):
    try:
        import keyring
        keyring.set_password(SERVICE_TROUSSEAU, email, mdp)
        return True
    except Exception:
        return False


def email_enregistre():
    return obtenir_parametre("garmin_email", "") or ""


def est_connecte():
    """Vrai si des jetons de connexion sont enregistrés (ne teste pas Internet)."""
    return DOSSIER_JETONS.exists() and any(DOSSIER_JETONS.glob("*"))


def se_connecter(email, mot_de_passe):
    """Première connexion (ou reconnexion) avec e-mail + mot de passe.
    Enregistre les jetons. Retourne le client."""
    if not bibliotheque_disponible():
        raise ErreurGarmin(
            "La bibliothèque « garminconnect » n'est pas installée. Relance l'installeur "
            "(ou : pip install garminconnect)."
        )
    from garminconnect import Garmin
    email = (email or "").strip()
    if not email or not mot_de_passe:
        raise ErreurGarmin("Renseigne l'adresse e-mail et le mot de passe de ton compte Garmin Connect.")
    try:
        g = Garmin(email, mot_de_passe, prompt_mfa=_refuser_mfa)
        DOSSIER_JETONS.mkdir(parents=True, exist_ok=True)
        # On repart de zéro : d'anciens jetons d'un autre compte ne doivent pas servir.
        for f in DOSSIER_JETONS.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        g.login(str(DOSSIER_JETONS))
        _sauver_jetons(g)
    except Exception as e:
        raise _traduire_erreur(e)
    definir_parametre("garmin_email", email)
    _ecrire_mdp_trousseau(email, mot_de_passe)
    return g


def client_connecte():
    """Client prêt à servir : jetons enregistrés, sinon mot de passe du
    trousseau, sinon SessionExpiree."""
    if not bibliotheque_disponible():
        raise ErreurGarmin(
            "La bibliothèque « garminconnect » n'est pas installée. Relance l'installeur."
        )
    from garminconnect import Garmin
    if est_connecte():
        try:
            g = Garmin(prompt_mfa=_refuser_mfa)
            g.login(str(DOSSIER_JETONS))
            _sauver_jetons(g)
            return g
        except Exception:
            pass   # jetons périmés : on tente le mot de passe du trousseau
    email = email_enregistre()
    mdp = _lire_mdp_trousseau(email) if email else None
    if email and mdp:
        return se_connecter(email, mdp)
    raise SessionExpiree("La session Garmin a expiré : reconnecte-toi avec ton mot de passe.")


def se_deconnecter():
    """Oublie jetons, mot de passe du trousseau et e-mail."""
    email = email_enregistre()
    if email:
        try:
            import keyring
            keyring.delete_password(SERVICE_TROUSSEAU, email)
        except Exception:
            pass
    shutil.rmtree(DOSSIER_JETONS, ignore_errors=True)
    definir_parametre("garmin_email", "")


# ------------------------------------------------------------------
# OUTILS
# ------------------------------------------------------------------

def _appel(fonction, *args):
    """Appelle l'API ; None si la donnée n'existe pas pour ce jour ; remonte
    seulement la limite de débit et la session expirée."""
    time.sleep(PAUSE_ENTRE_APPELS_S)
    try:
        return fonction(*args)
    except Exception as e:
        t = _traduire_erreur(e)
        if isinstance(t, (LimiteAtteinte, SessionExpiree)):
            raise t
        return None


def _get(objet, *chemin):
    for c in chemin:
        if isinstance(objet, dict):
            objet = objet.get(c)
        elif isinstance(objet, list) and isinstance(c, int) and -len(objet) <= c < len(objet):
            objet = objet[c]
        else:
            return None
    return objet


def _jours(debut, fin):
    d = debut
    while d <= fin:
        yield d
        d += timedelta(days=1)


STATUT_ENTRAINEMENT_FR = {
    "PRODUCTIVE": "Productif", "MAINTAINING": "Maintien", "RECOVERY": "Récupération",
    "UNPRODUCTIVE": "Improductif", "PEAKING": "Pic de forme", "OVERREACHING": "Surcharge",
    "DETRAINING": "Désentraînement", "NO_STATUS": "", "STRAINED": "Sous tension",
}
READINESS_FR = {"LOW": "Faible", "MODERATE": "Moyenne", "HIGH": "Élevée", "PRIME": "Optimale",
                "POOR": "Mauvaise", "FAIR": "Correcte", "GOOD": "Bonne", "EXCELLENT": "Excellente"}


# ------------------------------------------------------------------
# SANTÉ D'UN JOUR
# ------------------------------------------------------------------

def mesures_sante_jour(sommeil, hrv, stats, rhr):
    """Fusionne les réponses brutes de Garmin d'un jour en un enregistrement et
    en extrait les mesures avec le lecteur tolérant de l'import santé.
    Fonction pure (testable sans Internet)."""
    from data.import_sante_garmin import _extraire_jour, _nombre

    rec = {"sommeil": sommeil or {}, "hrv": hrv or {}, "stats": stats or {}}

    score = _get(sommeil, "dailySleepDTO", "sleepScores", "overall", "value")
    if score is not None:
        rec["overallScore"] = score
    resume_hrv = _get(hrv, "hrvSummary") or {}
    if resume_hrv.get("lastNightAvg") is not None:
        rec["avgOvernightHrv"] = resume_hrv["lastNightAvg"]
    if resume_hrv.get("status"):
        rec["hrvStatus"] = resume_hrv["status"]

    mesures = _extraire_jour(rec)

    if "fc_repos" not in mesures:
        valeur = _get(rhr, "allMetrics", "metricsMap", "WELLNESS_RESTING_HEART_RATE", 0, "value")
        v = _nombre(valeur, (30, 110), int)
        if v is not None:
            mesures["fc_repos"] = v
    return mesures


def extras_jour(stats, readiness, statut, vo2, poids_g):
    """Données en plus d'un jour -> dict (clés = colonnes de garmin_quotidien)
    ne gardant que les valeurs présentes et plausibles. Fonction pure."""
    from data.import_sante_garmin import _chercher, _nombre

    sortie = {}
    pas = _nombre(_get(stats, "totalSteps"), (0, 120000), int)
    if pas is not None and pas > 0:
        sortie["pas"] = pas
    cal = _nombre(_get(stats, "totalKilocalories"), (500, 12000), int)
    if cal is not None:
        sortie["calories_totales"] = cal
    mod = _get(stats, "moderateIntensityMinutes") or 0
    vig = _get(stats, "vigorousIntensityMinutes") or 0
    try:
        mi = int(mod) + int(vig)
    except (TypeError, ValueError):
        mi = 0
    if mi > 0:
        sortie["minutes_intenses"] = mi
    resp = _nombre(_get(stats, "avgWakingRespirationValue"), (4, 40), float)
    if resp is not None:
        sortie["respiration_moyenne"] = resp

    if readiness:
        premiere = readiness[0] if isinstance(readiness, list) and readiness else readiness
        sc = _nombre(_get(premiere, "score"), (0, 100), int)
        if sc is not None:
            sortie["readiness_score"] = sc
            niveau = str(_get(premiere, "level") or "").upper()
            sortie["readiness_niveau"] = READINESS_FR.get(niveau, niveau.capitalize())[:20]

    if statut:
        phrase = _chercher(statut, ("trainingStatusFeedbackPhrase",))
        if isinstance(phrase, str) and phrase:
            base = phrase.split("_")[0].upper()
            lib = STATUT_ENTRAINEMENT_FR.get(base, base.capitalize())
            if lib:
                sortie["statut_entrainement"] = lib

    if vo2:
        v = _nombre(_chercher(vo2, ("vo2MaxPreciseValue", "vo2MaxValue")), (15, 90), float)
        if v is not None:
            sortie["vo2max"] = v

    if poids_g:
        try:
            kg = float(poids_g) / 1000.0
        except (TypeError, ValueError):
            kg = None
        if kg and 30 <= kg <= 250:
            sortie["poids_kg"] = round(kg, 1)
    return sortie


def _enregistrer_extras(athlete_id, jour, extras):
    if not extras:
        return
    colonnes = list(extras)
    conn = connexion()
    try:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO garmin_quotidien (athlete_id, date) VALUES (?, ?)",
                    (athlete_id, jour))
        for c in colonnes:
            cur.execute(f"UPDATE garmin_quotidien SET {c}=? WHERE athlete_id=? AND date=?",
                        (extras[c], athlete_id, jour))
        # Le poids pesé alimente aussi le suivi corporel, sans jamais écraser une saisie.
        if "poids_kg" in extras:
            cur.execute("SELECT 1 FROM suivi_corporel WHERE athlete_id=? AND date=?", (athlete_id, jour))
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO suivi_corporel (athlete_id, date, poids_kg, notes) VALUES (?,?,?,?)",
                    (athlete_id, jour, extras["poids_kg"], "Pesée Garmin Connect"),
                )
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------
# SYNCHRO SANTÉ (plage de jours)
# ------------------------------------------------------------------

def synchro_sante(g, athlete_id, debut, fin, etat=None):
    """Récupère la santé de chaque jour de [debut, fin]. Retourne
    {'jours': n, 'mesures': {...}, 'dernier_ok': 'AAAA-MM-JJ'|None, 'arret': str|None}."""
    from data.import_sante_garmin import enregistrer_sante

    etat = etat if etat is not None else {}
    jours = list(_jours(debut, fin))
    etat.update(total=len(jours), fait=0)
    paquet = {}
    trouvees = {}
    dernier_ok = None
    arret = None
    limite_recente = fin - timedelta(days=JOURS_DETAIL_RECENT)
    nb_extras = 0

    def vider():
        if paquet:
            enregistrer_sante(athlete_id, dict(paquet))
            paquet.clear()

    try:
        for i, d in enumerate(jours):
            if etat.get("annuler"):
                arret = "Synchronisation annulée."
                break
            iso = d.isoformat()
            etat["msg"] = f"Santé du {d.strftime('%d/%m/%Y')}…"
            sommeil = _appel(g.get_sleep_data, iso)
            hrv = _appel(g.get_hrv_data, iso)
            stats = _appel(g.get_stats, iso)
            rhr = _appel(g.get_rhr_day, iso)
            mesures = mesures_sante_jour(sommeil, hrv, stats, rhr)
            if mesures:
                paquet[iso] = mesures
                for k in mesures:
                    trouvees[k] = trouvees.get(k, 0) + 1

            readiness = statut = vo2 = poids = None
            if d >= limite_recente:
                readiness = _appel(g.get_training_readiness, iso)
                statut = _appel(g.get_training_status, iso)
                vo2 = _appel(g.get_max_metrics, iso)
            poids_liste = _get(_appel(g.get_daily_weigh_ins, iso), "dateWeightList")
            if isinstance(poids_liste, list) and poids_liste:
                poids = _get(poids_liste, 0, "weight")
            extras = extras_jour(stats, readiness, statut, vo2, poids)
            if extras:
                _enregistrer_extras(athlete_id, iso, extras)
                nb_extras += 1

            dernier_ok = iso
            etat["fait"] = i + 1
            if len(paquet) >= 10:
                vider()
    except (LimiteAtteinte, SessionExpiree) as e:
        arret = str(e)
    finally:
        vider()
    return {"jours": etat.get("fait", 0), "mesures": trouvees, "dernier_ok": dernier_ok,
            "arret": arret, "jours_extras": nb_extras}


# ------------------------------------------------------------------
# SYNCHRO SORTIES
# ------------------------------------------------------------------

def _parser_debut_local(texte):
    try:
        return datetime.strptime(str(texte)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.fromisoformat(str(texte)[:19])
        except ValueError:
            return None


def _telecharger_fit(g, activite_id, dossier):
    """Télécharge le fichier d'origine d'une activité (zip contenant un .fit)
    et renvoie le chemin du .fit extrait, ou None."""
    brut = _appel(g.download_activity, str(activite_id), g.ActivityDownloadFormat.ORIGINAL)
    if not brut:
        return None
    zip_chemin = Path(dossier) / f"garmin_{activite_id}.zip"
    zip_chemin.write_bytes(brut)
    try:
        with zipfile.ZipFile(zip_chemin) as z:
            for info in z.infolist():
                if info.filename.lower().endswith(".fit"):
                    cible = Path(dossier) / f"garmin_{activite_id}.fit"
                    cible.write_bytes(z.read(info))
                    return cible
    except zipfile.BadZipFile:
        # Parfois Garmin renvoie directement le .fit
        cible = Path(dossier) / f"garmin_{activite_id}.fit"
        cible.write_bytes(brut)
        return cible
    finally:
        try:
            zip_chemin.unlink()
        except OSError:
            pass
    return None


def synchro_sorties(g, athlete_id, debut, fin, etat=None):
    """Importe / complète les sorties de [debut, fin]. Retourne
    {'nouvelles': n, 'completees': n, 'deja': n, 'erreurs': n, 'arret': str|None}."""
    from interface.import_montre_usb import (
        _trouver_activite_correspondante, analyser_dossier, importer_nouveau, completer_activite,
    )

    etat = etat if etat is not None else {}
    bilan = {"nouvelles": 0, "completees": 0, "deja": 0, "erreurs": 0, "arret": None}
    etat["msg"] = "Liste des sorties sur Garmin Connect…"
    try:
        liste = _appel(g.get_activities_by_date, debut.isoformat(), fin.isoformat()) or []
    except (LimiteAtteinte, SessionExpiree) as e:
        bilan["arret"] = str(e)
        return bilan
    liste = sorted(liste, key=lambda a: str(a.get("startTimeLocal", "")))
    etat.update(total=len(liste), fait=0)
    tmp = tempfile.mkdtemp(prefix="trailmaster_garmin_")
    try:
        for i, a in enumerate(liste):
            if etat.get("annuler"):
                bilan["arret"] = "Synchronisation annulée."
                break
            etat["fait"] = i
            aid = a.get("activityId")
            debut_local = _parser_debut_local(a.get("startTimeLocal"))
            distance_km = (a.get("distance") or 0) / 1000.0
            etat["msg"] = f"Sortie du {debut_local.strftime('%d/%m/%Y') if debut_local else '?'}…"
            if aid is None:
                continue
            corr = _trouver_activite_correspondante(athlete_id, debut_local, distance_km or None)
            if corr is not None and corr["a_une_trace"]:
                bilan["deja"] += 1
                continue
            try:
                fit = _telecharger_fit(g, aid, tmp)
                if fit is None:
                    bilan["erreurs"] += 1
                    continue
                dossier_une = Path(tmp) / f"a{aid}"
                dossier_une.mkdir(exist_ok=True)
                fit = Path(shutil.move(str(fit), str(dossier_une / fit.name)))
                for r in analyser_dossier(dossier_une, athlete_id):
                    if r["statut"] == "nouveau":
                        nouvel_id = importer_nouveau(r["chemin"], athlete_id, r["resume"], r["date_locale"])
                        c = connexion()
                        c.execute("UPDATE activites SET source='Garmin Connect', fichier_source=? WHERE id=?",
                                  (f"garmin_connect_{aid}", nouvel_id))
                        c.commit()
                        c.close()
                        bilan["nouvelles"] += 1
                    elif r["statut"] == "a_completer":
                        completer_activite(r["activite_id"], r["chemin"], r["champs_manquants"])
                        bilan["completees"] += 1
                    else:
                        bilan["deja"] += 1
            except (LimiteAtteinte, SessionExpiree) as e:
                bilan["arret"] = str(e)
                break
            except Exception:
                bilan["erreurs"] += 1
        else:
            etat["fait"] = len(liste)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bilan


# ------------------------------------------------------------------
# ORCHESTRATION
# ------------------------------------------------------------------

def _cle_derniere_sante(athlete_id):
    return f"garmin_sante_dernier_jour_{athlete_id}"


def derniere_synchro_sante(athlete_id):
    v = obtenir_parametre(_cle_derniere_sante(athlete_id))
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def derniere_synchro_texte():
    return obtenir_parametre("garmin_derniere_synchro", "") or ""


def synchroniser(athlete_id, jours_sorties=30, jours_sante=30, avec_sorties=True,
                 avec_sante=True, etat=None, g=None):
    """Synchronisation complète. `jours_*` = profondeur ; si la santé a déjà été
    synchronisée, on repart de quelques jours avant la dernière date
    récupérée (les valeurs déjà en base ne sont jamais écrasées, seules les
    cases vides se remplissent)."""
    etat = etat if etat is not None else {}
    aujourdhui = date.today()
    etat["msg"] = "Connexion à Garmin Connect…"
    try:
        g = g or client_connecte()
    except Exception as e:
        raise _traduire_erreur(e)

    resultat = {"sorties": None, "sante": None, "arret": None}

    if avec_sorties and not etat.get("annuler"):
        etat["phase"] = "sorties"
        resultat["sorties"] = synchro_sorties(
            g, athlete_id, aujourdhui - timedelta(days=jours_sorties), aujourdhui, etat)
        resultat["arret"] = resultat["sorties"].get("arret")

    if avec_sante and not etat.get("annuler") and not resultat["arret"]:
        etat["phase"] = "sante"
        debut = aujourdhui - timedelta(days=jours_sante)
        dernier = derniere_synchro_sante(athlete_id)
        if dernier is not None:
            debut = max(debut, dernier - timedelta(days=3)) if jours_sante < 300 else debut
        resultat["sante"] = synchro_sante(g, athlete_id, debut, aujourdhui, etat)
        ok = resultat["sante"].get("dernier_ok")
        if ok:
            definir_parametre(_cle_derniere_sante(athlete_id), ok)
        resultat["arret"] = resultat["sante"].get("arret")

    definir_parametre("garmin_derniere_synchro", datetime.now().strftime("%d/%m/%Y à %H:%M"))
    try:
        from interface.arriere_plan import vider_cache
        vider_cache()
    except Exception:
        pass
    etat["msg"] = "Terminé."
    return resultat


def synchro_auto_due():
    """Vrai si la synchro automatique est activée, qu'un compte est connecté et
    qu'elle n'a pas déjà tourné aujourd'hui."""
    if obtenir_parametre("garmin_synchro_auto", "0") != "1" or not est_connecte():
        return False
    return obtenir_parametre("garmin_auto_dernier_jour", "") != date.today().isoformat()


def marquer_synchro_auto():
    definir_parametre("garmin_auto_dernier_jour", date.today().isoformat())


def resume_texte(res):
    """Phrase française décrivant le résultat d'une synchro."""
    morceaux = []
    s = res.get("sorties")
    if s is not None:
        morceaux.append(
            f"Sorties : {s['nouvelles']} nouvelle(s), {s['completees']} complétée(s), "
            f"{s['deja']} déjà à jour" + (f", {s['erreurs']} en erreur" if s["erreurs"] else "") + "."
        )
    h = res.get("sante")
    if h is not None:
        if h["mesures"]:
            from data.import_sante_garmin import LIBELLES_MESURES
            detail = ", ".join(f"{LIBELLES_MESURES.get(k, k)} ({n} j)" for k, n in sorted(h["mesures"].items()))
            morceaux.append(f"Santé : {h['jours']} jour(s) lus — {detail}.")
        else:
            morceaux.append(f"Santé : {h['jours']} jour(s) lus, aucune mesure trouvée "
                            "(montre non portée, ou pas encore synchronisée avec le téléphone).")
    if res.get("arret"):
        morceaux.append("⚠️ " + res["arret"])
    return " ".join(morceaux) if morceaux else "Rien à synchroniser."
