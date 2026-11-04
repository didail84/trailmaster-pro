"""
Événements internes de Trail Hub Center.

Permet à un module de prévenir les autres qu'une donnée a changé, sans
les connaître : la base de données annonce « donnees_modifiees », et le
coach (cache forme / ACWR) ou l'interface (cache des calculs en
arrière-plan) s'abonnent pour vider leur cache.

C'est ce qui évite que data.database ou le noyau importent l'interface.
Un abonné qui plante ne bloque jamais l'émetteur ni les autres abonnés.

Événement utilisé aujourd'hui :
  DONNEES_MODIFIEES  — activités, imports ou synchro ont changé la base
                       (argument facultatif : athlete_id)
"""

import logging

DONNEES_MODIFIEES = "donnees_modifiees"

_abonnes = {}
_journal = logging.getLogger(__name__)


def abonner(nom_evenement, fonction):
    """Inscrit `fonction` ; sans effet si elle l'est déjà."""
    liste = _abonnes.setdefault(nom_evenement, [])
    if fonction not in liste:
        liste.append(fonction)


def desabonner(nom_evenement, fonction):
    liste = _abonnes.get(nom_evenement, [])
    if fonction in liste:
        liste.remove(fonction)


def emettre(nom_evenement, **arguments):
    """Appelle chaque abonné avec les arguments donnés."""
    for fonction in list(_abonnes.get(nom_evenement, [])):
        try:
            fonction(**arguments)
        except Exception:  # un abonné défaillant ne doit rien casser
            _journal.exception("Abonné en erreur pour l'événement %s", nom_evenement)
