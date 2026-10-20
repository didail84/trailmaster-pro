"""
E7 — Rapport PDF hebdomadaire ou mensuel : un document propre à garder,
imprimer ou envoyer à un coach / un médecin du sport. Fond blanc pour
l'impression. Tout est calculé localement.
"""

import html as _html
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QRectF, QSizeF, QMarginsF
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPen, QFont, QTextDocument, QPdfWriter, QPageSize, QPageLayout, QDesktopServices,
)
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QFileDialog, QTextBrowser

import data.metriques as met
from data.database import connexion
from interface.forme_evolution import _EcranAthlete
from interface.outils_ui import notifier

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
JOURS_COURTS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
ACCENT = "#2E7D32"


def _f(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def _h(h):
    return f"{int(h)} h {round((h - int(h)) * 60):02d}"


def _allure(v):
    return f"{int(v)}:{round((v - int(v)) * 60):02d} /km" if v else "—"


def _fmt_jour(d):
    return f"{d.day} {MOIS[d.month - 1]}"


def bornes(type_periode, ref):
    if type_periode == "semaine":
        d = ref - timedelta(days=ref.weekday())
        return d, d + timedelta(days=6)
    d = ref.replace(day=1)
    suiv = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)
    return d, suiv - timedelta(days=1)


def periode_precedente(type_periode, debut):
    if type_periode == "semaine":
        return bornes("semaine", debut - timedelta(days=7))
    return bornes("mois", debut - timedelta(days=1))


def _graphique_charge(valeurs, libelles, titre):
    """Barres de charge, fond blanc, 1400 × 520."""
    L, H = 1400, 520
    img = QImage(L, H, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = QFont("Helvetica")
    f.setPixelSize(30)
    p.setFont(f)
    p.setPen(QColor("#444"))
    p.drawText(QRectF(20, 8, L - 40, 44), Qt.AlignmentFlag.AlignLeft, titre)
    vmax = max(valeurs + [1])
    n = len(valeurs)
    zone = QRectF(40, 70, L - 80, H - 150)
    lb = zone.width() / n
    p.setPen(QPen(QColor("#DDD"), 2))
    p.drawLine(zone.left(), zone.bottom(), zone.right(), zone.bottom())
    for i, v in enumerate(valeurs):
        h = zone.height() * v / vmax
        r = QRectF(zone.left() + i * lb + lb * 0.15, zone.bottom() - h, lb * 0.7, max(h, 2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT) if v else QColor("#E5E5E5"))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QColor("#666"))
        p.drawText(QRectF(zone.left() + i * lb, zone.bottom() + 8, lb, 40), Qt.AlignmentFlag.AlignCenter, libelles[i])
        if v:
            p.setPen(QColor("#222"))
            p.drawText(QRectF(zone.left() + i * lb, r.top() - 38, lb, 34), Qt.AlignmentFlag.AlignCenter, str(round(v)))
    p.end()
    return img


def _evol(a, b, bas_meilleur=False):
    if a in (None, 0) or b is None:
        return ""
    pct = (b - a) / a * 100
    if abs(pct) < 1:
        return "="
    bon = (pct < 0) if bas_meilleur else (pct > 0)
    couleur = "#2E7D32" if bon else "#C62828"
    return f'<span style="color:{couleur}">{"▲" if pct > 0 else "▼"} {abs(round(pct))} %</span>'


def construire_rapport(athlete_id, type_periode="semaine", ref=None):
    """Renvoie (html, {nom_image: QImage})."""
    ref = ref or date.today()
    debut, fin = bornes(type_periode, ref)
    p_debut, p_fin = periode_precedente(type_periode, debut)
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT prenom, nom FROM athletes WHERE id=?", (athlete_id,))
    ath = cur.fetchone() or ("", "")
    conn.close()
    cur_ = met.totaux_periode(athlete_id, debut, min(fin, date.today()))
    prec = met.totaux_periode(athlete_id, p_debut, p_fin)
    sorties = met.activites_periode(athlete_id, debut, fin)

    titre = (f"Semaine du {_fmt_jour(debut)} au {_fmt_jour(fin)} {fin.year}" if type_periode == "semaine"
             else f"{MOIS[debut.month - 1].capitalize()} {debut.year}")
    images = {}

    # graphique de charge
    from interface.coach import obtenir_charges_journalieres
    nb = (date.today() - debut).days + 1
    par_jour = dict(obtenir_charges_journalieres(athlete_id, max(nb, 1)))
    if type_periode == "semaine":
        jours = [debut + timedelta(days=i) for i in range(7)]
        images["charge"] = _graphique_charge([par_jour.get(j, 0) for j in jours], JOURS_COURTS, "Charge d'entraînement par jour")
    else:
        sem, d = [], debut
        while d <= fin:
            f_ = min(d + timedelta(days=6), fin)
            sem.append((f"{d.day:02d}/{d.month:02d}", sum(v for j, v in par_jour.items() if d <= j <= f_)))
            d = f_ + timedelta(days=1)
        images["charge"] = _graphique_charge([v for _, v in sem], [l for l, _ in sem], "Charge d'entraînement par semaine")

    # forme
    from interface.coach import calculer_serie_forme, generer_alertes
    forme_txt = ""
    serie = calculer_serie_forme(athlete_id, nb_jours=max((date.today() - debut).days + 45, 60))
    if serie:
        fin_ref = min(fin, date.today())
        pts = [s for s in serie if s["date"] <= fin_ref]
        pts_debut = [s for s in serie if s["date"] <= debut]
        if pts:
            a, b = (pts_debut[-1] if pts_debut else pts[0]), pts[-1]
            forme_txt = (f"<tr><td>Forme (fitness)</td><td>{_f(a['fitness'])}</td><td>{_f(b['fitness'])}</td></tr>"
                         f"<tr><td>Fatigue</td><td>{_f(a['fatigue'])}</td><td>{_f(b['fatigue'])}</td></tr>"
                         f"<tr><td>Fraîcheur</td><td>{_f(a['forme'])}</td><td>{_f(b['forme'])}</td></tr>")

    # santé
    sante = []
    d = met.dette_sommeil(athlete_id, 14)
    if d["dette_h"] is not None:
        sante.append(f"Sommeil : moyenne {_f(d['moyenne_h'])} h par nuit, dette sur 14 jours {_f(d['dette_h'])} h (objectif {_f(d['objectif'])} h).")
    h = met.hrv_avec_bande(athlete_id, 60)
    if h["statut"]:
        sante.append("HRV de nuit (7 jours) : " + {"equilibree": "dans la bande normale", "basse": "sous la bande normale",
                                                    "haute": "au-dessus de la bande normale"}[h["statut"]] + f" ({round(h['moyenne_7j'])} ms).")
    fc = met.fc_repos_et_alerte(athlete_id, 60)
    if fc["ecart"] is not None:
        sante.append(f"FC de repos : {round(fc['derniere'])} bpm ({'+' if fc['ecart'] > 0 else '−'}{_f(abs(fc['ecart']))} bpm par rapport à ta base de {round(fc['base'])}).")
    pl = met.poids_lisse(athlete_id, 120)
    if pl["actuel"]:
        sante.append(f"Poids lissé : {_f(pl['actuel'])} kg" + (f" (tendance {'+' if pl['tendance_kg_sem'] > 0 else '−'}{_f(abs(pl['tendance_kg_sem']), 2)} kg/semaine)" if pl["tendance_kg_sem"] is not None else "") + ".")
    conn = connexion()
    cur = conn.cursor()
    cur.execute("SELECT zone_corporelle, type_blessure FROM blessures WHERE athlete_id=? AND statut='En cours'", (athlete_id,))
    for z, t in cur.fetchall():
        sante.append(f"Blessure en cours : {z}{' — ' + t if t else ''}.")
    conn.close()
    cm = met.monotonie_contrainte(athlete_id, 6)
    comp = [m for m in cm if m["monotonie"] is not None and not m["partielle"]]
    if comp:
        sante.append(f"Monotonie de la dernière semaine complète : {_f(comp[-1]['monotonie'], 2)}.")
    r = met.repartition_facile_dur(athlete_id, 8)
    if r["pct_facile"] is not None:
        sante.append(f"Temps passé facile sur 8 semaines : {r['pct_facile']} % (objectif ≈ 80 %).")

    alertes = [a for a in generer_alertes(athlete_id) if a["niveau"] in ("critique", "attention")]

    # objectifs annuels
    objectifs = [x for x in met.progression_annuelle(athlete_id, debut.year) if x.get("cible")]

    def ligne(lib, cle, fmt, bas=False):
        a, b = prec.get(cle), cur_.get(cle)
        return (f"<tr><td>{lib}</td><td align='right'>{fmt(b) if b is not None else '—'}</td>"
                f"<td align='right' style='color:#777'>{fmt(a) if a is not None else '—'}</td>"
                f"<td align='right'>{_evol(a, b, bas)}</td></tr>")

    rows_sorties = "".join(
        f"<tr><td>{s['jour'].strftime('%d/%m') if s['jour'] else ''}</td><td>{_html.escape((s['nom'] or s['type'] or '')[:34])}</td>"
        f"<td>{s['type'] or ''}</td><td align='right'>{_f(s['distance'])}</td><td align='right'>{s['denivele']}</td>"
        f"<td align='right'>{_h(s['duree'] / 3600) if s['duree'] else '—'}</td>"
        f"<td align='right'>{_allure(s['allure']) if s['allure'] else '—'}</td><td align='right'>{s['fc_moy'] or '—'}</td></tr>"
        for s in sorties) or "<tr><td colspan='8'><i>Aucune sortie sur cette période.</i></td></tr>"

    html = f"""
    <html><body style="font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #222;">
    <table width="100%"><tr><td><span style="font-size:9pt; color:{ACCENT}; font-weight:bold;">TRAILMASTER PRO · RAPPORT {'HEBDOMADAIRE' if type_periode == 'semaine' else 'MENSUEL'}</span><br>
    <span style="font-size:22pt; font-weight:bold;">{_html.escape(titre)}</span><br>
    <span style="color:#666;">{_html.escape(ath[0])} {_html.escape(ath[1])} · édité le {date.today().strftime('%d/%m/%Y')}</span></td></tr></table>
    <hr>
    <h3 style="color:{ACCENT};">Résumé</h3>
    <table width="100%" cellspacing="0" cellpadding="5" border="0">
    <tr style="background-color:#F0F4F0;"><th align="left"></th><th align="right">Cette période</th><th align="right">Précédente</th><th align="right">Évolution</th></tr>
    {ligne('Sorties', 'sorties', lambda v: str(int(v)))}
    {ligne('Distance', 'distance', lambda v: _f(v) + ' km')}
    {ligne('Dénivelé positif', 'denivele', lambda v: f'{int(v)} m')}
    {ligne('Durée', 'duree_h', _h)}
    {ligne('Charge', 'charge', lambda v: str(int(v)))}
    {ligne('Allure course/trail', 'allure_course', _allure, True)}
    </table>
    <p><img src="img:charge" width="640"></p>
    {'<h3 style="color:' + ACCENT + ';">Forme</h3><table width="60%" cellspacing="0" cellpadding="5"><tr style="background-color:#F0F4F0;"><th align="left"></th><th>Début</th><th>Fin</th></tr>' + forme_txt + '</table>' if forme_txt else ''}
    <h3 style="color:{ACCENT};">Sorties</h3>
    <table width="100%" cellspacing="0" cellpadding="4">
    <tr style="background-color:#F0F4F0;"><th align="left">Date</th><th align="left">Sortie</th><th align="left">Type</th><th align="right">km</th><th align="right">D+</th><th align="right">Durée</th><th align="right">Allure</th><th align="right">FC</th></tr>
    {rows_sorties}
    </table>
    {'<h3 style="color:' + ACCENT + ';">Santé et récupération</h3><ul>' + ''.join('<li>' + _html.escape(x) + '</li>' for x in sante) + '</ul>' if sante else ''}
    {'<h3 style="color:#C62828;">Points d&#39;attention</h3><ul>' + ''.join('<li>' + _html.escape(a['message']) + '</li>' for a in alertes) + '</ul>' if alertes else ''}
    {'<h3 style="color:' + ACCENT + ';">Objectifs ' + str(debut.year) + '</h3><ul>' + ''.join('<li>' + _html.escape(o['libelle']) + ' : ' + _f(o['realise'], 0) + ' / ' + _f(o['cible'], 0) + ' ' + o['unite'] + ' (' + str(round(o['pct'])) + ' %)</li>' for o in objectifs) + '</ul>' if objectifs else ''}
    <p style="color:#999; font-size:8pt;">Rapport généré localement par TrailMaster Pro. Les indicateurs de charge et de forme sont des repères d'entraînement, pas un avis médical.</p>
    </body></html>
    """
    return html, images


def ecrire_pdf(html, images, chemin):
    doc = QTextDocument()
    for nom, img in images.items():
        doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(f"img:{nom}"), img)
    doc.setHtml(html)
    pdf = QPdfWriter(str(chemin))
    pdf.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    pdf.setPageMargins(QMarginsF(14, 12, 14, 12), QPageLayout.Unit.Millimeter)
    pdf.setResolution(150)
    doc.setPageSize(QSizeF(pdf.width(), pdf.height()))
    doc.print_(pdf)


class RapportPDF(_EcranAthlete):

    def __init__(self, athlete_id_initial=None):
        super().__init__("📄  Rapport PDF",
                         "Un rapport propre de ta semaine ou de ton mois (sorties, charge, forme, sommeil, alertes), "
                         "prêt à enregistrer, imprimer ou envoyer à ton coach.", athlete_id_initial)
        self.combo_type = QComboBox()
        self.combo_type.addItem("Hebdomadaire", "semaine")
        self.combo_type.addItem("Mensuel", "mois")
        self.combo_periode = QComboBox()
        self.combo_type.currentIndexChanged.connect(self._remplir_periodes)
        self.combo_periode.currentIndexChanged.connect(self.actualiser)
        self.barre.insertWidget(2, self.combo_type)
        self.barre.insertWidget(3, self.combo_periode)
        b = QPushButton("💾 Enregistrer en PDF…")
        b.setObjectName("boutonPrincipal")
        b.clicked.connect(self._enregistrer)
        self.barre.addWidget(b)
        self.apercu = QTextBrowser()
        self.apercu.setMinimumHeight(700)
        self.principal.addWidget(self.apercu, 1)
        self._html = None
        self._images = {}
        self._remplir_periodes()
        self._finaliser()

    def _remplir_periodes(self):
        t = self.combo_type.currentData()
        self.combo_periode.blockSignals(True)
        self.combo_periode.clear()
        ref = date.today()
        for i in range(0, 12):
            if t == "semaine":
                d, f = bornes("semaine", ref - timedelta(weeks=i))
                self.combo_periode.addItem(f"{'Cette semaine' if i == 0 else 'Semaine du ' + d.strftime('%d/%m')} ({_fmt_jour(d)} – {_fmt_jour(f)})", d)
            else:
                m0 = ref.year * 12 + ref.month - 1 - i
                an, mo = divmod(m0, 12)
                d = date(an, mo + 1, 1)
                self.combo_periode.addItem(f"{MOIS[mo].capitalize()} {an}", d)
        self.combo_periode.blockSignals(False)
        if self.athlete_id is not None or hasattr(self, "_html"):
            self.actualiser()

    def actualiser(self):
        a = self.athlete_id
        if a is None or self.combo_periode.currentData() is None:
            self.apercu.setHtml("<p>Choisis un athlète.</p>")
            self._html = None
            return
        self._html, self._images = construire_rapport(a, self.combo_type.currentData(), self.combo_periode.currentData())
        doc = self.apercu.document()
        for nom, img in self._images.items():
            doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(f"img:{nom}"), img)
        self.apercu.setHtml(self._html)

    def _enregistrer(self):
        if not self._html:
            return
        d = self.combo_periode.currentData()
        defaut = str(Path.home() / f"Rapport_{self.combo_type.currentData()}_{d.isoformat()}.pdf")
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer le rapport", defaut, "PDF (*.pdf)")
        if chemin:
            ecrire_pdf(self._html, self._images, chemin)
            notifier("Rapport PDF enregistré", parent=self)
            QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))
