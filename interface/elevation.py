"""
Récupération d'altitude via Open-Elevation (https://open-elevation.com)
— gratuit, sans clé API. Utilisé pour donner un profil altimétrique aux
parcours dessinés à la main (le tracé lui-même n'a pas d'altitude
native, contrairement à une trace GPS enregistrée).

Service public sans garantie de disponibilité — en cas d'échec, on
retombe sur une altitude à 0 partout plutôt que de bloquer l'enregistrement
du parcours.
"""

import json
import urllib.request
import urllib.error

from interface.erreurs_reseau import message_erreur_reseau


URL_ELEVATION = "https://api.open-elevation.com/api/v1/lookup"


def obtenir_altitudes(points_latlon, taille_lot=100):
    """points_latlon : liste de (lat, lon). Retourne (liste_altitudes,
    erreur) — liste_altitudes est toujours de la même longueur que
    points_latlon (0.0 en cas d'échec), pour ne jamais bloquer
    l'enregistrement d'un parcours à cause d'un service externe indisponible."""

    if not points_latlon:
        return [], None

    altitudes = [0.0] * len(points_latlon)
    derniere_erreur = None

    for debut in range(0, len(points_latlon), taille_lot):
        lot = points_latlon[debut:debut + taille_lot]
        corps = json.dumps({
            "locations": [{"latitude": lat, "longitude": lon} for lat, lon in lot]
        }).encode("utf-8")

        requete = urllib.request.Request(
            URL_ELEVATION, data=corps,
            headers={"Content-Type": "application/json"}, method="POST",
        )

        try:
            with urllib.request.urlopen(requete, timeout=20) as reponse:
                donnees = json.loads(reponse.read().decode("utf-8"))
            for i, resultat in enumerate(donnees.get("results", [])):
                if debut + i < len(altitudes):
                    altitudes[debut + i] = resultat.get("elevation", 0.0)
        except urllib.error.URLError as erreur:
            derniere_erreur = message_erreur_reseau(erreur)
        except Exception as erreur:
            derniere_erreur = f"Réponse inattendue du service d'altitude : {erreur}"

    return altitudes, derniere_erreur
