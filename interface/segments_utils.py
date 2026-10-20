"""
Segments précis : contrairement au module Secteurs (qui regroupe des
sorties par simple proximité de leur point de départ), un segment ici
est un tronçon précis d'un parcours — on cherche si ce même tronçon a
été parcouru dans d'autres sorties, pour comparer les temps.

Principe de la détection :
  1. Un segment de référence est extrait d'une trace existante entre
     deux indices de points, puis sous-échantillonné tous les ~50 m
     pour obtenir une poignée de points repères.
  2. Pour chercher ce segment dans une autre trace, on cherche un point
     de la trace proche du premier point repère (rayon de tolérance),
     puis on avance repère par repère : chaque repère suivant doit se
     retrouver, dans une fenêtre de points à venir, à moins du rayon de
     tolérance. Si tous les repères sont retrouvés dans l'ordre, c'est
     un passage sur le segment ; la durée est la différence de temps
     relatif entre le premier et le dernier point apparié.

Limites à connaître :
  - Un parcours en aller-retour où le segment est traversé deux fois
    n'est détecté qu'une seule fois (le premier passage trouvé).
  - Sans temps par point, la durée ne peut pas être calculée (mais la
    détection géométrique, elle, fonctionne quand même) — dans ce cas
    le passage est ignoré puisqu'on ne peut rien comparer.
"""

from interface.gpx_utils import _distance_haversine_km


PAS_ECHANTILLONNAGE_M = 50
RAYON_TOLERANCE_M = 25
FENETRE_RECHERCHE_POINTS = 400


def extraire_reference_segment(points, index_debut, index_fin):
    """Découpe points[index_debut:index_fin+1] et le sous-échantillonne
    tous les ~50 m. Retourne None si la plage est trop courte."""

    sous_liste = points[index_debut:index_fin + 1]
    if len(sous_liste) < 2:
        return None

    reference = [sous_liste[0]]
    distance_depuis_dernier = 0.0
    distance_totale_m = 0.0
    denivele_positif = 0.0

    for i in range(1, len(sous_liste)):
        p1, p2 = sous_liste[i - 1], sous_liste[i]
        d = _distance_haversine_km(p1[0], p1[1], p2[0], p2[1]) * 1000
        distance_totale_m += d
        distance_depuis_dernier += d

        diff_alt = p2[2] - p1[2]
        if diff_alt > 0.5:
            denivele_positif += diff_alt

        if distance_depuis_dernier >= PAS_ECHANTILLONNAGE_M:
            reference.append(p2)
            distance_depuis_dernier = 0.0

    if reference[-1][:2] != sous_liste[-1][:2]:
        reference.append(sous_liste[-1])

    if distance_totale_m < 100:
        return None  # trop court pour être un segment utile (<100m)

    return {
        "points_reference": [(p[0], p[1]) for p in reference],
        "distance_km": round(distance_totale_m / 1000, 3),
        "denivele_positif": round(denivele_positif),
    }


def detecter_occurrence(points_reference, trace_points, rayon_m=RAYON_TOLERANCE_M,
                         fenetre=FENETRE_RECHERCHE_POINTS):
    """Cherche une séquence dans trace_points qui suit points_reference
    dans l'ordre. Retourne (index_debut, index_fin) ou None."""

    if len(trace_points) < 2 or len(points_reference) < 2:
        return None

    candidats_depart = [
        i for i, p in enumerate(trace_points)
        if _distance_haversine_km(p[0], p[1], points_reference[0][0], points_reference[0][1]) * 1000 <= rayon_m
    ]

    for depart in candidats_depart:
        index_courant = depart
        succes = True

        for ref_point in points_reference[1:]:
            limite = min(index_courant + fenetre, len(trace_points))
            trouve = None
            for j in range(index_courant, limite):
                d = _distance_haversine_km(
                    trace_points[j][0], trace_points[j][1], ref_point[0], ref_point[1]
                ) * 1000
                if d <= rayon_m:
                    trouve = j
                    break
            if trouve is None:
                succes = False
                break
            index_courant = trouve

        if succes:
            return depart, index_courant

    return None


def duree_occurrence_s(trace_points, index_debut, index_fin):
    """Durée en secondes entre index_debut et index_fin, à partir du
    temps relatif par point. None si cette info n'est pas disponible."""

    p_debut = trace_points[index_debut]
    p_fin = trace_points[index_fin]

    if len(p_debut) < 4 or len(p_fin) < 4 or p_debut[3] is None or p_fin[3] is None:
        return None

    duree = p_fin[3] - p_debut[3]
    return duree if duree > 0 else None
