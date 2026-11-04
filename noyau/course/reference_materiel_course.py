"""
Génération d'une liste de matériel obligatoire/conseillé pour une
course de trail, à partir de sa distance, son dénivelé et quelques
conditions (portion nocturne, haute montagne, saison).

IMPORTANT — ce que c'est et ce que ce n'est PAS : chaque organisateur
de course fixe lui-même son propre règlement et sa propre liste de
matériel obligatoire (affichée sur le site officiel de la course), et
ces listes varient d'une épreuve à l'autre. Ce module ne reproduit PAS
le règlement exact d'une course précise — il applique des règles
générales calibrées sur les standards habituels du trail français
(type UTMB/ITRA), pour donner un bon repère par défaut. Le conseil
donné dans l'écran est donc toujours de vérifier le règlement officiel
de la course visée en complément.

calculer_materiel(...) renvoie deux listes ordonnées, chacune composée
de (nom_de_l_item, raison_courte) :
  - "obligatoire" : ce qui est quasi-systématiquement exigé par les
    organisateurs à ce niveau de distance/conditions.
  - "conseille" : ce qui n'est en général pas exigé mais fortement
    recommandé.
"""


def calculer_materiel(distance_km, denivele_m=0, nocturne=False, altitude_elevee=False, saison=None):
    distance_km = distance_km or 0
    denivele_m = denivele_m or 0

    obligatoire = []
    conseille = []

    def ajouter_obligatoire(nom, raison):
        if nom not in [o[0] for o in obligatoire]:
            obligatoire.append((nom, raison))

    def ajouter_conseille(nom, raison):
        if nom not in [c[0] for c in conseille]:
            conseille.append((nom, raison))

    # --- Toute distance ---
    ajouter_obligatoire("Téléphone portable chargé", "Numéro des secours joignable à tout moment — quasi systématique désormais, même sur les courses courtes.")
    ajouter_conseille("Pièce d'identité", "Utile en cas de prise en charge par les secours.")

    # --- Paliers de distance (cumulatifs) ---
    if distance_km >= 15:
        ajouter_obligatoire("Gobelet personnel réutilisable", "Les gobelets jetables sont interdits sur la grande majorité des trails dès les ravitaillements.")
        ajouter_obligatoire("Réserve d'eau (0,5 L minimum)", "Autonomie minimale entre deux ravitaillements.")
    else:
        ajouter_conseille("Gobelet personnel réutilisable", "De plus en plus souvent demandé, même sur les courses courtes.")
        ajouter_conseille("Petite réserve d'eau", "Utile si la météo est chaude ou les ravitaillements espacés.")

    if distance_km >= 30:
        ajouter_obligatoire("Réserve d'eau (1 L minimum)", "Autonomie accrue, ravitaillements plus espacés sur ce type de format.")
        ajouter_obligatoire("Couverture de survie", "Exigée sur la quasi-totalité des formats à partir du semi-trail.")
        ajouter_conseille("Coupe-vent léger", "Utile dès que le parcours prend de l'altitude ou en cas de vent.")
        ajouter_conseille("Barres/gels énergétiques personnels", "Pour ne pas dépendre uniquement des ravitaillements officiels.")

    if distance_km >= 50:
        ajouter_obligatoire("Lampe frontale + pile/batterie de rechange", "Exigée même sans portion nocturne prévue au départ, en cas de retard sur l'horaire.")
        ajouter_obligatoire("Sifflet", "Signal de détresse standard, exigé sur la plupart des formats longs.")
        ajouter_obligatoire("Veste imperméable à capuche (coutures étanches)", "Protection contre la pluie/le vent en cas de passage en altitude ou de météo changeante.")
        ajouter_obligatoire("Réserve de nourriture personnelle", "Au-delà des ravitaillements officiels, pour gérer un éventuel coup de moins bien.")
        ajouter_conseille("Bâtons de marche", "Très utile dès que le dénivelé devient conséquent.")
        ajouter_conseille("Guêtres / anti-frottement", "Confort sur les longues distances techniques.")

    if distance_km >= 80:
        ajouter_obligatoire("Pantalon long ou jambières", "Protection contre le froid en cas d'arrivée de nuit ou d'altitude, exigée sur la plupart des ultra-trails.")
        ajouter_obligatoire("Deuxième réserve d'eau", "Autonomie renforcée entre les ravitaillements les plus espacés d'un ultra.")
        ajouter_obligatoire("Bonnet ou buff couvrant les oreilles", "Protection contre le froid nocturne/altitude, exigée sur la plupart des ultra-trails.")
        ajouter_obligatoire("Gants", "Protection contre le froid, exigée sur la plupart des ultra-trails.")
        ajouter_conseille("Deuxième lampe frontale (ou piles supplémentaires)", "Sécurité en cas de panne sur une portion nocturne longue.")
        ajouter_conseille("Vêtement chaud supplémentaire (type doudoune légère)", "Pour les arrêts aux ravitaillements de nuit ou en altitude.")
        ajouter_conseille("Vaseline / crème anti-frottement", "Indispensable au confort sur ce type de durée d'effort.")

    # --- Dénivelé ---
    if denivele_m >= 2000:
        ajouter_conseille("Bâtons de marche", "Fortement recommandés au-delà de 2000 m de D+.")
        ajouter_conseille("Lunettes de soleil", "Réverbération en altitude.")

    # --- Portion nocturne ---
    if nocturne:
        ajouter_obligatoire("Lampe frontale + pile/batterie de rechange", "Portion nocturne annoncée pour cette course.")
        ajouter_conseille("Vêtement chaud supplémentaire (type doudoune légère)", "Les températures chutent nettement la nuit, même en été.")

    # --- Haute montagne / altitude ---
    if altitude_elevee:
        ajouter_obligatoire("Veste chaude supplémentaire", "Terrain de haute montagne : chute de température rapide possible.")
        ajouter_obligatoire("Gants", "Terrain de haute montagne.")
        ajouter_obligatoire("Bonnet ou buff couvrant les oreilles", "Terrain de haute montagne.")
        ajouter_conseille("Bâtons de marche", "Très utile en terrain de haute montagne.")

    # --- Saison ---
    if saison == "Hiver":
        ajouter_conseille("Gants chauds", "Risque de froid marqué en hiver.")
        ajouter_conseille("Guêtres", "Utile en cas de neige ou de terrain boueux hivernal.")
        ajouter_conseille("Crampons légers (type chaînes à neige pour chaussures)", "Si neige ou verglas annoncés sur le parcours.")
    elif saison == "Été":
        ajouter_conseille("Casquette ou chapeau", "Protection contre le soleil en cas de forte chaleur.")
        ajouter_conseille("Crème solaire", "Protection contre le soleil en cas de forte chaleur.")
        ajouter_conseille("Pastilles de sel / électrolytes", "Pertes hydriques et salines accrues en cas de forte chaleur.")

    return {"obligatoire": obligatoire, "conseille": conseille}
