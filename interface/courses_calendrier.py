"""
Calendrier de courses de trail à venir, pour repérer une course qui
correspond à la préparation en cours plutôt que de chercher soi-même
sur des dizaines de sites différents.

Contrairement au reste de l'appli, cette liste n'est PAS mise à jour
toute seule : scraper de façon fiable des dizaines de sites de
calendriers/clubs, chacun avec sa propre structure et changeant
régulièrement, n'est pas réaliste à automatiser dans une appli locale.
La liste est donc peuplée « à la main » (recherche ponctuelle), avec la
possibité d'ajouter/retirer des courses soi-même comme n'importe quel
autre écran de suivi.

Le score d'intérêt est calculé localement (sans IA, sans réseau) en
comparant la distance et le dénivelé de chaque course à ce que
l'athlète a déjà couru récemment (120 derniers jours) — une course
largement à sa portée ou au contraire très au-delà de ce qu'il a déjà
fait obtient un score plus bas qu'une course ambitieuse mais jouable.
"""

from datetime import date, timedelta

from PySide6.QtWidgets import QMessageBox

from noyau.course.estimation_temps_course import estimer_temps_course
from interface.ecran_liste import EcranListe, Champ
from interface.materiel_course import MaterielCourse
from noyau.donnees import activites as dact  # accès aux données
from noyau.donnees import courses as dcourse


REGIONS = ["Provence-Alpes-Côte d'Azur", "Auvergne-Rhône-Alpes", "Occitanie", "Autre"]


def _plus_grosses_sorties_recentes(athlete_id, jours=120):
    """Retourne (plus_longue_distance_km, plus_gros_denivele_m) parmi les
    sorties Trail/Course/Randonnée des N derniers jours de l'athlète."""

    limite = (date.today() - timedelta(days=jours)).isoformat()
    resultat = dact.maxima_depuis(athlete_id, limite)

    if not resultat:
        return 0.0, 0
    return resultat[0] or 0.0, resultat[1] or 0


def _score_sur_ratio(ratio):
    """Un ratio proche de 1 (course proche de ce qui a déjà été couru)
    est jugé "dans les cordes" — un ratio nettement supérieur reste
    intéressant (objectif ambitieux) mais moins immédiatement adapté ;
    un ratio très inférieur est peu challengeant."""

    if ratio is None:
        return 50  # pas de référence récente -> score neutre, ni positif ni négatif
    if ratio <= 0.35:
        return 40
    if ratio <= 1.2:
        return 100 - abs(ratio - 0.8) * 30
    if ratio <= 1.8:
        return 75 - (ratio - 1.2) * 60
    return max(15, 40 - (ratio - 1.8) * 15)


def _calculer_score_interet(id_ligne, valeurs):
    resultat = dcourse.course(id_ligne, "athlete_id", "distance_km", "denivele_m")

    if not resultat or resultat[0] is None:
        return "—"

    athlete_id, distance_km, denivele_m = resultat
    plus_longue, plus_gros_dplus = _plus_grosses_sorties_recentes(athlete_id)

    ratio_distance = (distance_km / plus_longue) if (distance_km and plus_longue) else None
    ratio_denivele = (denivele_m / plus_gros_dplus) if (denivele_m and plus_gros_dplus) else None

    scores = [s for s in (_score_sur_ratio(ratio_distance), _score_sur_ratio(ratio_denivele)) if s is not None]
    if not scores:
        return "— (pas assez de sorties récentes pour comparer)"

    score = round(sum(scores) / len(scores))

    if score >= 80:
        étiquette = "🟢 Bien dans tes cordes"
    elif score >= 55:
        étiquette = "🟡 Ambitieuse mais jouable"
    elif score <= 45 and (ratio_distance or 0) <= 0.35:
        étiquette = "🔵 Plutôt facile pour toi"
    else:
        étiquette = "🟠 Gros objectif, prépa spécifique nécessaire"

    return f"{score}/100 — {étiquette}"


def _calculer_temps_estime(id_ligne, valeurs):
    resultat = dcourse.course(id_ligne, "athlete_id", "date", "distance_km", "denivele_m")

    if not resultat or resultat[0] is None:
        return "—"

    athlete_id, date_course, distance_km, denivele_m = resultat
    estimation = estimer_temps_course(athlete_id, distance_km, denivele_m, date_course=date_course)
    if not estimation:
        return "— (pas assez d'historique Trail/Course sur 2 ans)"

    texte = estimation["duree_formatee"]
    if estimation["ajustement_saison"]:
        texte += " (ajusté à la saison)"
    if estimation["extrapolation"]:
        texte += " ⚠️ bien au-delà de tes sorties habituelles"
    return texte


def _voir_materiel_pour_course(ecran):
    ligne = ecran.table.currentRow()
    if ligne < 0:
        QMessageBox.information(ecran, "Sélection requise", "Sélectionne d'abord une course dans la liste.")
        return

    id_course = ecran.lignes_ids[ligne]
    resultat = dcourse.course(id_course, "athlete_id", "nom", "date", "distance_km", "denivele_m", "type_terrain")
    if not resultat:
        return

    athlete_id, nom, date_, distance_km, denivele_m, type_terrain = resultat
    ecran._fenetre_materiel = MaterielCourse(
        athlete_id_initial=athlete_id,
        course_preselectionnee={
            "id": id_course, "nom": nom, "date": date_, "distance_km": distance_km,
            "denivele_m": denivele_m, "type_terrain": type_terrain,
        },
    )
    ecran._fenetre_materiel.show()


def _ouvrir_roadbook_pour_course(ecran):
    """Ouvre le Roadbook (GPX, barrières, ravitaillements, fiche) pour la course sélectionnée."""
    ligne = ecran.table.currentRow()
    if ligne < 0:
        QMessageBox.information(ecran, "Sélection requise", "Sélectionne d'abord une course dans la liste.")
        return
    r = dcourse.course(ecran.lignes_ids[ligne], "athlete_id", "nom", "date", "distance_km", "denivele_m")
    if not r:
        return
    from interface.roadbook import RoadbookCourse
    ecran._fenetre_roadbook = RoadbookCourse(
        athlete_id_initial=r[0],
        course_preselectionnee={"nom": r[1], "date": r[2], "distance_km": r[3], "denivele_m": r[4]})
    ecran._fenetre_roadbook.show()


class CoursesCalendrier(EcranListe):

    def __init__(self, athlete_id_initial=None):
        champs = [
            Champ("nom", "Nom de la course", "texte", obligatoire=True),
            Champ("date", "Date", "date"),
            Champ("lieu", "Lieu", "texte"),
            Champ("region", "Région", "choix", choix=REGIONS),
            Champ("distance_km", "Distance (km)", "decimal"),
            Champ("denivele_m", "D+ (m)", "entier"),
            Champ("type_terrain", "Type de terrain", "texte"),
            Champ("lien", "Lien", "texte"),
            Champ("source", "Source", "texte"),
            Champ("notes", "Notes", "texte_long"),
        ]
        super().__init__(
            titre="Courses à venir",
            sous_titre=(
                "Trails à venir en Provence-Alpes-Côte d'Azur, Auvergne-Rhône-Alpes et Occitanie — "
                "liste constituée manuellement (pas de mise à jour automatique), score d'intérêt "
                "calculé par rapport à tes sorties récentes"
            ),
            icone="🏁",
            table_sql="courses_calendrier",
            champs=champs,
            athlete_id_initial=athlete_id_initial,
            tri="date ASC",
            colonnes_calculees=[
                {"label": "Score d'intérêt", "fonction": _calculer_score_interet},
                {"label": "Temps estimé", "fonction": _calculer_temps_estime},
            ],
            bouton_extra=[("🎒 Voir le matériel conseillé", _voir_materiel_pour_course),
                          ("🗺️ Roadbook de cette course", _ouvrir_roadbook_pour_course)],
        )

        from interface.analyse_ia_widget import CarteAnalyseIA
        from data import analyse_ecran as _ae
        self.carte_ia = CarteAnalyseIA("courses", "préparation aux courses", lambda: self.combo_athlete.currentData(),
                                       lambda: _ae.dossier_courses(self.combo_athlete.currentData()))
        self.zone_haut.addWidget(self.carte_ia)
