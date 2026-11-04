"""
Analyse d'une sortie sans IA (moteur de règles hors ligne, gratuit).

Utilisée quand aucune clé Gemini/Groq n'est réglée, ou quand l'IA ne
répond pas : la sortie reçoit quand même une analyse écrite, tirée
uniquement des chiffres calculés par le logiciel (même dossier que
celui envoyé à l'IA). Aucune valeur n'est inventée ; chaque phrase
cite son chiffre. Les estimations (zones, nature de la séance) sont
dites comme telles.

Le texte ne contient volontairement pas le titre « Lecture technique »
des analyses IA : dès qu'une clé est réglée, une analyse IA peut donc
remplacer celle-ci (voir noyau/ia/analyse_auto.py).
"""

MARQUEUR_ANALYSE_LOCALE = "Analyse hors ligne"


def _v(d, *chemin):
    for c in chemin:
        if not isinstance(d, dict):
            return None
        d = d.get(c)
    return d


def _nb(x, dec=0):
    if x is None:
        return "?"
    if dec == 0:
        return f"{round(x):d}".replace("-", "−")
    return f"{x:.{dec}f}".replace(".", ",").replace("-", "−")


def rediger(resume):
    """Texte Markdown à partir du résumé de sortie (ia_coach.construire_resume_sortie)."""
    a = resume.get("activite") or {}
    tech = resume.get("dossier_technique") or {}
    lecture, forts, travail, conseils = [], [], [], []

    dist, dplus, duree = a.get("distance_km") or 0, a.get("denivele_positif_m") or 0, a.get("duree_min") or 0
    nature = tech.get("nature_probable_de_la_seance")
    if dist:
        ligne = f"{_nb(dist, 1)} km et {_nb(dplus)} m de D+ en {int(duree // 60)} h {int(duree % 60):02d}"
        km_effort = _v(tech, "effort", "km_effort")
        if km_effort:
            ligne += f", soit {_nb(km_effort, 1)} km-effort"
        lecture.append(ligne + ".")
    if nature:
        lecture.append(f"Nature probable de la séance (estimation) : {nature}.")

    pct_fc = _v(tech, "effort", "FC_moyenne_pct_FCmax")
    if pct_fc:
        lecture.append(f"FC moyenne {a.get('fc_moyenne')} bpm, soit {pct_fc} % de ta FC max.")
    facile = _v(tech, "zones_FC", "pct_facile_Z1_Z2")
    intense = _v(tech, "zones_FC", "pct_intense_Z4_Z5")
    if facile is not None and intense is not None:
        lecture.append(f"Temps en zones (estimation) : {facile} % en Z1-Z2, {intense} % en Z4-Z5.")
        if nature and "endurance" in nature.lower() and intense > 25:
            travail.append(f"{intense} % du temps en Z4-Z5 pour une sortie d'endurance : l'allure facile était trop rapide.")
        if facile >= 75:
            forts.append(f"{facile} % du temps en zones faciles : bonne base d'endurance (modèle 80/20).")

    reg = _v(tech, "trace", "allure_ajustee_pente", "regularite") or {}
    gap = _v(tech, "trace", "allure_ajustee_pente", "allure_ajustee_GAP")
    if gap:
        lecture.append(f"Allure ajustée à la pente (estimation) : {gap} min/km.")
    ecart = reg.get("ecart_moitiés_s_km")
    profil = reg.get("profil")
    if profil and ecart is not None:
        if ecart <= 10:
            forts.append(f"Allure régulière : {ecart} s/km d'écart entre les deux moitiés ({profil}).")
        elif "positif" in profil:
            travail.append(f"La 2e moitié est plus lente de {ecart} s/km : départ trop rapide ou fatigue en fin de sortie.")

    dec = _v(tech, "trace", "decouplage_cardiaque_Pa_Hr", "pct")
    if dec is not None and duree >= 60:
        if dec < 5:
            forts.append(f"Découplage cardiaque de {_nb(dec, 1)} % (moins de 5 %) : endurance aérobie solide sur cette durée.")
        elif dec > 8:
            travail.append(f"Découplage cardiaque de {_nb(dec, 1)} % (plus de 8 %) : limite aérobie, chaleur ou fatigue en fin de sortie.")

    comp = tech.get("comparaison_sorties_similaires") or {}
    eff = comp.get("efficacite_vs_similaires_pct")
    if eff is not None and comp.get("nb_sorties_comparees"):
        n = comp["nb_sorties_comparees"]
        if eff >= 3:
            forts.append(f"Efficacité meilleure de {_nb(eff, 1)} % que tes {n} sorties similaires récentes.")
        elif eff <= -3:
            travail.append(f"Efficacité en baisse de {_nb(-eff, 1)} % par rapport à tes {n} sorties similaires récentes "
                           "(même vitesse pour plus de battements, ou plus lent à FC égale).")
        else:
            lecture.append(f"Efficacité proche de tes {n} sorties similaires récentes ({'+' if eff >= 0 else ''}{_nb(eff, 1)} %).")

    fr = _v(tech, "charge_et_fraicheur_au_jour_J", "fraicheur_TSB")
    hausse = _v(tech, "charge_et_fraicheur_au_jour_J", "variation_hebdo_pct")
    if fr is not None:
        lecture.append(f"Fraîcheur (TSB) le jour de la sortie : {_nb(fr, 1)}.")
        if fr < -30:
            conseils.append("Fraîcheur sous −30 : prévois 1 à 2 jours faciles ou de repos avant la prochaine séance dure.")
    if hausse is not None and hausse > 25:
        conseils.append(f"Charge des 7 derniers jours en hausse de {hausse} % : limite la hausse à 10 % la semaine prochaine.")

    acwr = _v(resume, "acwr", "acwr")
    if acwr:
        if acwr > 1.5:
            conseils.append(f"ACWR à {_nb(acwr, 2)} (au-dessus de 1,5) : risque de blessure accru, allège les prochains jours.")
        elif acwr < 0.8:
            conseils.append(f"ACWR à {_nb(acwr, 2)} : charge en retrait, tu peux relancer progressivement.")

    rec = tech.get("recuperation_avant_la_seance") or {}
    if rec.get("HRV_vs_base") == "sous la bande":
        conseils.append("VFC de nuit sous ta bande habituelle : récupération incomplète, garde la prochaine séance facile.")
    ecart_fc = rec.get("FC_repos_ecart_vs_base_bpm")
    if ecart_fc is not None and ecart_fc >= 5:
        conseils.append(f"FC de repos plus haute de {_nb(ecart_fc, 1)} bpm que d'habitude : signe de fatigue, surveille demain matin.")
    som = resume.get("sommeil_moyen_recent_h")
    if som is not None and som < 6.5:
        conseils.append(f"Sommeil moyen récent de {_nb(som, 1)} h : vise 7 h ou plus avant les séances dures.")

    bless = resume.get("blessures_actives") or []
    if bless:
        zones = ", ".join(f"{b.get('zone') or ''} {b.get('type') or ''}".strip() for b in bless)
        conseils.insert(0, f"Blessure en cours ({zones}) : elle prime sur la progression ; arrête si la douleur augmente.")

    if a.get("notes_athlete"):
        lecture.append(f"Ta note : « {a['notes_athlete']} ».")

    morceaux = [f"### {MARQUEUR_ANALYSE_LOCALE} : lecture de la séance"]
    morceaux += [f"- {x}" for x in lecture] or ["- Pas assez de chiffres sur cette sortie."]
    if forts:
        morceaux += ["", "### Points forts"] + [f"- {x}" for x in forts]
    if travail:
        morceaux += ["", "### Points à travailler"] + [f"- {x}" for x in travail]
    morceaux += ["", "### Pour la suite"] + ([f"- {x}" for x in conseils] or
                                              ["- Rien de particulier à signaler : continue ton plan prévu."])
    morceaux += ["", "_Analyse calculée par les règles du logiciel, sans IA. Les zones, l'allure ajustée et la nature "
                     "de la séance sont des estimations._"]
    return "\n".join(morceaux)


def analyser_sortie_hors_ligne(activite_id, athlete_id):
    """Texte de l'analyse hors ligne, ou None si la sortie n'existe pas."""
    from noyau.ia.ia_coach import construire_resume_sortie
    resume = construire_resume_sortie(activite_id, athlete_id)
    return rediger(resume) if resume else None
