"""
Mini-fiche Roadbook à imprimer (v108) : format A5, gros caractères, à glisser
dans une pochette plastifiée ou à plastifier. Dessinée avec QPainter dans un PDF :
rien ne quitte l'ordinateur.

Page 1 : course, temps estimé, profil, points de passage (heure estimée, barrière, marge).
Page 2 (et suivantes si besoin) : quoi manger / boire sur chaque tronçon, checklist du sac.
Les chiffres sont des estimations : à lire comme un repère, pas comme un chrono.
"""

from PySide6.QtCore import Qt, QRectF, QPointF, QMarginsF
from PySide6.QtGui import QPdfWriter, QPageSize, QPainter, QColor, QFont, QPen, QBrush, QPolygonF, QPageLayout

from noyau.course.roadbook import texte_duree, texte_heure

NOIR = QColor("#111111")
GRIS = QColor("#666666")
GRIS_CLAIR = QColor("#E4E4E4")
ROUGE = QColor("#C62828")
ORANGE = QColor("#E65100")
VERT = QColor("#2E7D32")
BLEU = QColor("#1565C0")

RESOLUTION = 300
MM = RESOLUTION / 25.4


def _police(pt, gras=False):
    f = QFont("Helvetica")
    f.setPixelSize(max(6, int(pt * RESOLUTION / 72)))
    f.setBold(gras)
    return f


def _virgule(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


class _Page:
    """Petit curseur vertical qui change de page quand il n'y a plus de place."""

    def __init__(self, writer, p, entete):
        self.w, self.p, self.entete = writer, p, entete
        self.L = writer.width()
        self.H = writer.height()
        self.y = 0.0
        self.num = 1

    def reste(self):
        return self.H - self.y

    def saut_si_besoin(self, hauteur_mm):
        if self.y + hauteur_mm * MM > self.H:
            self.w.newPage()
            self.num += 1
            self.y = 0.0
            self.titre_court()

    def titre_court(self):
        p = self.p
        p.setPen(NOIR)
        p.setFont(_police(11, True))
        p.drawText(QRectF(0, self.y, self.L, 6 * MM), Qt.AlignmentFlag.AlignLeft, self.entete)
        p.setPen(QPen(GRIS_CLAIR, 2))
        p.drawLine(0, int(self.y + 7 * MM), self.L, int(self.y + 7 * MM))
        self.y += 9 * MM

    def texte(self, txt, pt=10, gras=False, couleur=NOIR, x=0.0, largeur=None, marge_bas=1.5):
        p = self.p
        p.setFont(_police(pt, gras))
        p.setPen(couleur)
        largeur = largeur if largeur is not None else self.L - x
        r = p.boundingRect(QRectF(x, self.y, largeur, 1000 * MM),
                           int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap), txt)
        self.saut_si_besoin(r.height() / MM + marge_bas)
        p.drawText(QRectF(x, self.y, largeur, r.height()),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap), txt)
        self.y += r.height() + marge_bas * MM
        return r.height()


def _profil(page, trace_prof, passages, hauteur_mm=42):
    """Profil altimétrique avec un repère numéroté par point de passage."""
    p = page.p
    if len(trace_prof) < 2:
        return
    page.saut_si_besoin(hauteur_mm + 4)
    x0, y0, w, h = 8 * MM, page.y, page.L - 8 * MM, hauteur_mm * MM
    kms = [k for k, _ in trace_prof]
    alts = [a for _, a in trace_prof]
    kmax = max(kms) or 1.0
    amin, amax = min(alts), max(alts)
    amin_aff = amin - (amax - amin) * 0.08
    amax_aff = amax + (amax - amin) * 0.12 + 1
    ech_x = lambda km: x0 + w * km / kmax
    ech_y = lambda a: y0 + h - h * (a - amin_aff) / (amax_aff - amin_aff)
    poly = QPolygonF([QPointF(x0, y0 + h)] + [QPointF(ech_x(k), ech_y(a)) for k, a in trace_prof]
                     + [QPointF(x0 + w, y0 + h)])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#D6E4F5")))
    p.drawPolygon(poly)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(BLEU, 3))
    p.drawPolyline(QPolygonF([QPointF(ech_x(k), ech_y(a)) for k, a in trace_prof]))
    # axes
    p.setPen(QPen(GRIS, 2))
    p.drawLine(int(x0), int(y0 + h), int(x0 + w), int(y0 + h))
    p.setFont(_police(7))
    p.drawText(QRectF(0, y0 - 1 * MM, 8 * MM, 4 * MM), Qt.AlignmentFlag.AlignLeft, f"{int(amax)}")
    p.drawText(QRectF(0, y0 + h - 4 * MM, 8 * MM, 4 * MM), Qt.AlignmentFlag.AlignLeft, f"{int(amin)}")
    pas = 5 if kmax <= 40 else 10 if kmax <= 100 else 20
    k = pas
    while k < kmax:
        p.drawLine(int(ech_x(k)), int(y0 + h), int(ech_x(k)), int(y0 + h + 1.2 * MM))
        p.drawText(QRectF(ech_x(k) - 6 * MM, y0 + h + 1.2 * MM, 12 * MM, 4 * MM),
                   Qt.AlignmentFlag.AlignHCenter, f"{k}")
        k += pas
    # repères
    for i, pt in enumerate(passages, 1):
        if pt["type"] == "Repère" and i not in (1, len(passages)):
            continue
        x = ech_x(min(pt["km"], kmax))
        couleur = ROUGE if pt["statut"] in ("depasse",) else ORANGE if pt["statut"] == "serre" else NOIR
        p.setPen(QPen(couleur, 2, Qt.PenStyle.DashLine))
        p.drawLine(int(x), int(y0), int(x), int(y0 + h))
        p.setBrush(QBrush(couleur))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(x, y0 + 2.5 * MM), 2.6 * MM, 2.6 * MM)
        p.setPen(QColor("white"))
        p.setFont(_police(7, True))
        p.drawText(QRectF(x - 2.6 * MM, y0 - 0.1 * MM, 5.2 * MM, 5.2 * MM), Qt.AlignmentFlag.AlignCenter, str(i))
        p.setBrush(Qt.BrushStyle.NoBrush)
    page.y = y0 + h + 6 * MM


def _tableau_passages(page, passages):
    p = page.p
    cols = [("#", 8), ("Point", 52), ("Km", 15), ("Passage", 20), ("Barrière", 20), ("Marge", 21)]  # mm, total 136
    total = sum(c[1] for c in cols)
    echelle = (page.L / MM) / total
    larg = [c[1] * echelle * MM for c in cols]

    def entete():
        page.saut_si_besoin(9)
        p.setFont(_police(8, True))
        p.setPen(GRIS)
        x = 0.0
        for (nom, _), l in zip(cols, larg):
            p.drawText(QRectF(x, page.y, l, 5 * MM), Qt.AlignmentFlag.AlignLeft, nom)
            x += l
        p.setPen(QPen(NOIR, 3))
        p.drawLine(0, int(page.y + 5.5 * MM), page.L, int(page.y + 5.5 * MM))
        page.y += 7 * MM

    entete()
    for i, pt in enumerate(passages, 1):
        hauteur = 8.5
        if page.y + hauteur * MM > page.H:
            page.saut_si_besoin(hauteur + 20)
            entete()
        y = page.y
        statut = pt["statut"]
        if i % 2 == 0:
            p.fillRect(QRectF(0, y - 0.8 * MM, page.L, (hauteur) * MM), QColor("#F4F4F4"))
        marge_txt, couleur = "", NOIR
        if pt["marge_min"] is not None:
            m = pt["marge_min"]
            marge_txt = f"{'−' if m < 0 else '+'}{abs(m) // 60}h{abs(m) % 60:02d}" if abs(m) >= 60 else f"{'−' if m < 0 else '+'}{abs(m)} min"
            if statut == "depasse":
                marge_txt += " !!"
                couleur = ROUGE
            elif statut == "serre":
                marge_txt += " !"
                couleur = ORANGE
            else:
                couleur = VERT
        nom = pt["nom"]
        if pt["type"] == "Ravitaillement":
            nom = "R · " + nom
        elif pt["type"] == "Barrière horaire":
            nom = "B · " + nom
        elif pt["type"] == "Assistance":
            nom = "A · " + nom
        valeurs = [str(i), nom, _virgule(pt["km"]), texte_heure(pt["passage"]),
                   texte_heure(pt["barriere"]) if pt["barriere"] else "—", marge_txt or "—"]
        x = 0.0
        for k, (v, l) in enumerate(zip(valeurs, larg)):
            p.setFont(_police(10 if k != 1 else 10, k in (3, 5)))
            p.setPen(couleur if k == 5 else NOIR)
            p.drawText(QRectF(x, y, l - 1 * MM, hauteur * MM), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                       p.fontMetrics().elidedText(v, Qt.TextElideMode.ElideRight, int(l - 1.5 * MM)))
            x += l
        page.y += hauteur * MM


def rendre_fiche_pdf(chemin, rb, passages, trace_prof, nutrition_lignes, checklist, scenarios=None, sacs=None):
    """rb : {nom, date_course, depart, distance_km, denivele_m, temps_total_s, allure_plat}.
    scenarios / sacs : facultatifs (noyau/course/strategie.py). Retourne le nombre de pages."""
    w = QPdfWriter(chemin)
    w.setPageSize(QPageSize(QPageSize.PageSizeId.A5))
    w.setResolution(RESOLUTION)
    w.setPageMargins(QMarginsF(6, 6, 6, 6), QPageLayout.Unit.Millimeter)
    w.setTitle(f"Roadbook – {rb.get('nom', '')}")
    p = QPainter(w)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    page = _Page(w, p, rb.get("nom", "Roadbook"))

    # ---------- page 1
    p.setPen(NOIR)
    page.texte(rb.get("nom", "Roadbook"), 17, True, marge_bas=1)
    ligne = []
    if rb.get("date_course"):
        ligne.append(str(rb["date_course"]))
    if rb.get("depart"):
        ligne.append(f"départ {rb['depart']}")
    if rb.get("distance_km"):
        ligne.append(f"{_virgule(rb['distance_km'])} km")
    if rb.get("denivele_m"):
        ligne.append(f"D+ {int(rb['denivele_m'])} m")
    page.texte("  ·  ".join(ligne), 10, couleur=GRIS, marge_bas=1)
    if rb.get("temps_total_s"):
        arr = passages[-1]["passage"] if passages else None
        page.texte(f"Temps estimé {texte_duree(rb['temps_total_s'])}"
                   + (f"  ·  arrivée vers {texte_heure(arr)}" if arr else ""), 12, True,
                   marge_bas=1 if scenarios else 3)
    if scenarios:
        page.texte("  ·  ".join(f"{sc['libelle']} {texte_duree(sc['temps_s'])} (arrivée {texte_heure(sc['passages'][-1]['passage'])})"
                                for sc in scenarios.values()), 9, couleur=GRIS, marge_bas=3)
    _profil(page, trace_prof, passages)
    _tableau_passages(page, passages)
    page.texte("R = ravitaillement · B = barrière horaire · A = assistance · marge = barrière − passage estimé "
               "(! = moins de 30 min). Estimations : garde de la réserve.", 7.5, couleur=GRIS, marge_bas=0)

    # ---------- page 2
    p.setPen(NOIR)
    w.newPage()
    page.num += 1
    page.y = 0.0
    page.titre_court()
    if nutrition_lignes:
        page.texte("Manger / boire entre les points", 13, True, marge_bas=2)
        for i, n in enumerate(nutrition_lignes, 2):
            page.texte(f"→ {n['nom']} (km {_virgule(n['km'])}) · {texte_duree(n['troncon_s'])} · "
                       f"{n['glucides_g']} g de glucides · {n['eau_ml']} ml", 9.5, True, marge_bas=0.3)
            page.texte(n["texte"], 9, couleur=GRIS, x=3 * MM, marge_bas=2)
        page.texte("Aliments génériques, glucides indicatifs : vérifie les étiquettes et teste tout à "
                   "l'entraînement.", 7.5, couleur=GRIS, marge_bas=3)
    if sacs:
        page.texte("Sacs d'assistance", 13, True, marge_bas=2)
        for sac in sacs:
            h = sac["heures"]
            page.texte(f"{sac['nom']} (km {_virgule(sac['km'])}) — arrivée {texte_heure(h['ambitieux'])} à "
                       f"{texte_heure(h['prudent'])}, plutôt vers {texte_heure(h['realiste'])}", 9.5, True, marge_bas=0.3)
            page.texte(f"Jusqu'à {sac['jusqua']} · {texte_duree(sac['duree_s'])}", 8.5, couleur=GRIS, x=3 * MM, marge_bas=0.5)
            for ligne in sac["lignes"]:
                page.texte("• " + ligne, 8.5, x=3 * MM, marge_bas=0.4)
            page.y += 1.5 * MM
    if checklist:
        page.texte("Checklist du sac", 13, True, marge_bas=2)
        section = None
        for it in checklist:
            if it["section"] != section:
                section = it["section"]
                page.texte(section, 10, True, couleur=BLEU, marge_bas=1)
            page.saut_si_besoin(7)
            y = page.y
            p.setPen(QPen(NOIR, 3))
            p.setBrush(QBrush(NOIR) if it.get("coche") else Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(0, y + 0.6 * MM, 4 * MM, 4 * MM))
            p.setBrush(Qt.BrushStyle.NoBrush)
            page.texte(it["texte"], 9.5, x=6 * MM, marge_bas=0.8)
    p.end()
    return page.num


# ----------------------------------------------------------------------
# Bracelet d'allures (Trail Hub Center, étape 3)
# ----------------------------------------------------------------------
LARGEUR_BRACELET_MM = 32


def rendre_bracelet_pdf(chemin, nom_course, lignes, depart=""):
    """Bande de 32 mm de large à découper et à scotcher sur l'avant-bras (ou à glisser
    sous un bracelet en silicone) : une ligne par point — km, nom, heure réaliste en gros,
    heure prudente et barrière en petit, D+ / D− jusqu'au point suivant.
    Quatre bandes identiques par feuille A4. Retourne le nombre de pages."""
    w = QPdfWriter(chemin)
    w.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    w.setResolution(RESOLUTION)
    w.setPageMargins(QMarginsF(8, 8, 8, 8), QPageLayout.Unit.Millimeter)
    w.setTitle(f"Bracelet d'allures – {nom_course}")
    p = QPainter(w)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    largeur = LARGEUR_BRACELET_MM * MM
    ecart = 12 * MM
    hauteur_ligne = 11.5 * MM
    entete = 13 * MM
    H = w.height()
    par_page = max(1, int((H - entete) // hauteur_ligne))
    pages = [lignes[i:i + par_page] for i in range(0, len(lignes), par_page)] or [[]]
    for n, bloc in enumerate(pages):
        if n:
            w.newPage()
        for copie in range(4):
            x0 = copie * (largeur + ecart)
            if x0 + largeur > w.width():
                break
            p.setPen(QPen(GRIS, 2, Qt.PenStyle.DashLine))     # trait de coupe
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(x0, 0, largeur, entete + len(bloc) * hauteur_ligne))
            p.setPen(NOIR)
            p.setFont(_police(8, True))
            p.drawText(QRectF(x0 + 1.5 * MM, 1 * MM, largeur - 3 * MM, 6 * MM),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), nom_course[:26])
            p.setFont(_police(6))
            p.setPen(GRIS)
            p.drawText(QRectF(x0 + 1.5 * MM, 6.5 * MM, largeur - 3 * MM, 5 * MM),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       (f"départ {depart} · " if depart else "") + "réaliste / prudent")
            for i, l in enumerate(bloc):
                y = entete + i * hauteur_ligne
                if i % 2 == 0:
                    p.fillRect(QRectF(x0 + 0.5, y, largeur - 1, hauteur_ligne), QColor("#F2F2F2"))
                couleur = ROUGE if l["barriere"] else NOIR
                p.setPen(couleur)
                p.setFont(_police(7, True))
                p.drawText(QRectF(x0 + 1.2 * MM, y + 0.6 * MM, 11 * MM, 4.5 * MM),
                           int(Qt.AlignmentFlag.AlignLeft), _virgule(l["km"]))
                p.setFont(_police(6.2))
                p.drawText(QRectF(x0 + 10 * MM, y + 0.6 * MM, largeur - 11 * MM, 4.5 * MM),
                           int(Qt.AlignmentFlag.AlignLeft), l["nom"][:18])
                p.setPen(NOIR)
                p.setFont(_police(11, True))
                p.drawText(QRectF(x0 + 1.2 * MM, y + 4.2 * MM, 17 * MM, 6.5 * MM),
                           int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), l["realiste"])
                p.setFont(_police(6.2))
                p.setPen(GRIS)
                bas = l["prudent"] + (f"  B {l['barriere']}" if l["barriere"] else "")
                p.drawText(QRectF(x0 + 17.5 * MM, y + 4.4 * MM, largeur - 18 * MM, 3.2 * MM),
                           int(Qt.AlignmentFlag.AlignLeft), bas)
                if l["suite_dplus"] is not None:
                    p.drawText(QRectF(x0 + 17.5 * MM, y + 7.4 * MM, largeur - 18 * MM, 3.2 * MM),
                               int(Qt.AlignmentFlag.AlignLeft), f"+{l['suite_dplus']} −{l['suite_dmoins']}")
    p.end()
    return len(pages)
