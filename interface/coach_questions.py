"""
E9 — Questions libres au coach IA. Un résumé de la situation (calculé
localement : forme, charge, sommeil, blessures, objectifs, dernières
sorties) est joint à la question ; seule cette synthèse part vers l'IA
(Gemini / Groq, clés déjà configurées dans Réglages), jamais la base.
"""

import html as _html
from datetime import date, timedelta

from PySide6.QtWidgets import QTextBrowser, QLineEdit, QPushButton, QHBoxLayout, QLabel

import data.metriques as met
from interface.forme_evolution import _EcranAthlete
from interface.tache_ia import TacheAnalyseIA

QUESTIONS_TYPES = [
    "Suis-je prêt pour une grosse sortie ce week-end ?",
    "Ma charge de la semaine est-elle raisonnable ?",
    "Que dois-je améliorer en priorité ?",
    "Comment va ma récupération ?",
    "Mon entraînement est-il assez varié ?",
]


def contexte_local(athlete_id):
    """Synthèse textuelle de la situation de l'athlète (aucun nom, aucune donnée brute)."""
    from interface.coach import calculer_serie_forme, generer_alertes
    L = []
    a = met._athlete(athlete_id)
    L.append(f"Athlète : {a.get('age', '?')} ans, FC max {a.get('fc_max')}, FC repos {a.get('fc_repos')}, VMA {a.get('vma')}.")
    s = calculer_serie_forme(athlete_id, 90)
    if s:
        L.append(f"Forme : fitness {s[-1]['fitness']}, fatigue {s[-1]['fatigue']}, fraîcheur {s[-1]['forme']}.")
    for lib, n in (("7 derniers jours", 7), ("28 derniers jours", 28)):
        t = met.totaux_periode(athlete_id, date.today() - timedelta(days=n - 1), date.today())
        L.append(f"{lib} : {t['sorties']} sorties, {t['distance']} km, {t['denivele']} m D+, {t['duree_h']} h, charge {t['charge']}.")
    try:
        r = met.repartition_facile_dur(athlete_id, 8)
        if r["pct_facile"] is not None:
            L.append(f"Part de temps facile sur 8 semaines : {r['pct_facile']} %.")
        d = met.dette_sommeil(athlete_id, 14)
        if d["moyenne_h"]:
            L.append(f"Sommeil moyen {d['moyenne_h']} h, dette {d['dette_h']} h.")
        f = met.fc_repos_et_alerte(athlete_id, 60)
        if f["ecart"] is not None:
            L.append(f"FC de repos : {f['ecart']:+.1f} bpm par rapport à la base.")
        h = met.hausse_charge_hebdo(athlete_id, 6)
        L.append("Variation de charge hebdo : " + ", ".join(f"{x['variation_pct']:+d} %" for x in h if x["variation_pct"] is not None))
    except Exception:
        pass
    for al in generer_alertes(athlete_id):
        if al["niveau"] in ("critique", "attention"):
            L.append("Alerte : " + al["message"])
    for c in met.courses_a_venir(athlete_id)[:3]:
        L.append(f"Course à venir : {c['nom']} le {c['date']} ({c['distance_km']} km, {c['denivele_m'] or 0} m D+).")
    recent = met.activites_periode(athlete_id, date.today() - timedelta(days=14))[-8:]
    for x in recent:
        L.append(f"Sortie {str(x['date'])[:10]} : {x['type']} {x['distance']:.1f} km, {x['denivele']} m D+, {x['duree'] // 60} min, FC {x['fc_moy'] or '?'}.")
    return "\n".join(L)


def construire_prompt(question, contexte):
    return ("Tu es un entraîneur de trail expérimenté, bienveillant et prudent. Réponds en français, de façon concrète et courte "
            "(10 lignes maximum), en t'appuyant uniquement sur les données ci-dessous. Si une donnée manque, dis-le. "
            "Ne pose aucun diagnostic médical.\n\nDONNÉES :\n" + contexte + "\n\nQUESTION : " + question)


class QuestionsCoach(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("💬  Questions au coach",
                         "Pose une question libre : le coach répond d'après ta situation réelle (forme, charge, sommeil, blessures, sorties récentes).",
                         athlete_id_initial)
        self.fil = QTextBrowser()
        self.fil.setMinimumHeight(480)
        self.principal.addWidget(self.fil, 1)
        rangee = QHBoxLayout()
        for q in QUESTIONS_TYPES:
            b = QPushButton(q)
            b.clicked.connect(lambda _=False, t=q: self.poser(t))
            rangee.addWidget(b)
        self.principal.addLayout(rangee)
        saisie = QHBoxLayout()
        self.champ = QLineEdit()
        self.champ.setPlaceholderText("Écris ta question…")
        self.champ.returnPressed.connect(lambda: self.poser(self.champ.text()))
        self.bouton = QPushButton("Envoyer")
        self.bouton.setObjectName("boutonPrincipal")
        self.bouton.clicked.connect(lambda: self.poser(self.champ.text()))
        saisie.addWidget(self.champ, 1)
        saisie.addWidget(self.bouton)
        self.principal.addLayout(saisie)
        self._html = ""
        self._tache = None
        self._finaliser()

    def actualiser(self):
        pass

    def _ajouter(self, qui, texte):
        t = _html.escape(texte).replace("\n", "<br>")
        coul = "#2E7D32" if qui == "Coach" else "#888"
        self._html += f"<p><b style='color:{coul}'>{qui}</b><br>{t}</p>"
        self.fil.setHtml(self._html)
        self.fil.verticalScrollBar().setValue(self.fil.verticalScrollBar().maximum())

    def poser(self, question, fonction=None):
        question = (question or "").strip()
        a = self.athlete_id
        if not question or a is None or self._tache is not None:
            return
        self.champ.clear()
        self._ajouter("Toi", question)
        self.bouton.setEnabled(False)
        prompt = construire_prompt(question, contexte_local(a))
        from interface.ia_coach import _appeler_ia
        self._tache = TacheAnalyseIA(fonction or (lambda: _appeler_ia(prompt)), self)
        self._tache.reussite.connect(self._reponse)
        self._tache.echec.connect(self._echec)
        self._tache.start()

    def _fin(self):
        self._tache = None
        self.bouton.setEnabled(True)

    def _reponse(self, res):
        texte = res[0] if isinstance(res, (tuple, list)) else res
        self._fin()
        self._ajouter("Coach", str(texte).strip())

    def _echec(self, msg):
        self._fin()
        self._ajouter("Coach", "⚠️ " + msg)
