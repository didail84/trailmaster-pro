"""
Règles d'adaptation automatique de la charge de musculation — reprises
telles quelles du programme Excel importé (feuilles "Adaptation
automatique" et "Mode d'emploi") :

  - RPE ≤ 6 (et douleur ≤ 4)  -> séance facile, augmenter la charge de 2,5 à 5 %
  - RPE 7-8                    -> effort conforme, conserver
  - RPE ≥ 9                    -> effort trop élevé, réduire de 5 à 10 %
  - Douleur 1 à 4/10            -> surveiller, ne pas augmenter
  - Douleur ≥ 5/10               -> stopper l'exercice, ne pas progresser

RPE = Ressenti d'effort perçu sur la dernière série (échelle de 6 à 10,
voir barème dans l'écran : 6 = facile, 10 = échec).
"""


def proposer_charge_suivante(charge_actuelle, rpe, douleur):
    """Retourne (charge_proposee_kg, decision_texte)."""

    if charge_actuelle is None:
        charge_actuelle = 0.0

    if douleur is not None and douleur >= 5:
        return charge_actuelle, "⚠️ Douleur ≥5/10 : stopper cet exercice, ne pas progresser."

    if rpe is not None and rpe >= 9:
        nouvelle = round(charge_actuelle * 0.925, 1)
        return nouvelle, "Effort trop élevé (RPE≥9) : réduire la charge de ~5-10 %."

    if douleur is not None and 1 <= douleur <= 4:
        return charge_actuelle, "Douleur légère : ne pas augmenter, surveiller et adapter si ça persiste."

    if rpe is not None and rpe <= 6:
        nouvelle = round(charge_actuelle * 1.0375, 1)
        return nouvelle, "Séance facile (RPE≤6) : augmenter la charge de ~2,5-5 %."

    return charge_actuelle, "Effort conforme (RPE 7-8) : conserver la charge prévue."
