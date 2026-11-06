"""
Reçu de cotisation (étape 4.1) : une page A4 avec le club, l'adhérent, la
saison, la licence, le montant et le mode de paiement. Mise en page HTML
imprimée par Qt (pas de bibliothèque à installer).
"""

import html
from datetime import date

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from noyau.club import categories as cat


def _e(v):
    return html.escape(str(v or ""))


def _euros(v):
    t = f"{v or 0:,.2f}".replace(",", " ").replace(".", ",")
    return t + " €"


def _jour(d):
    try:
        return date.fromisoformat(str(d)[:10]).strftime("%d/%m/%Y") if d else ""
    except ValueError:
        return str(d)


def html_recu(club, a):
    club = club or {}
    adresse_club = " ".join(x for x in (club.get("adresse"), club.get("code_postal"), club.get("ville")) if x)
    c = cat.categorie(a.get("date_naissance"), a.get("saison"))
    lignes = [("Saison", a.get("saison")),
              ("Licence", cat.LIBELLE_LICENCE.get(a.get("type_licence"), "—")),
              ("N° de licence", a.get("numero_licence") or "—"),
              ("Catégorie", f"{c['libelle']} ({c['code']})" if c else "—"),
              ("Tarif", a.get("tarif") or "—"),
              ("Montant reçu", _euros(a.get("montant_paye"))),
              ("Mode de paiement", a.get("paiement_mode") or "—"),
              ("Date du paiement", _jour(a.get("paiement_date")) or "—")]
    tableau = "".join(f"<tr><td style='color:#555;padding:6px 18px 6px 0'>{_e(k)}</td>"
                      f"<td style='padding:6px 0'><b>{_e(v)}</b></td></tr>" for k, v in lignes)
    return f"""
<div style="font-family:Helvetica,Arial,sans-serif;color:#111;font-size:11pt">
<table width="100%"><tr>
<td><span style="font-size:18pt;font-weight:bold">{_e(club.get('nom') or 'Club')}</span><br>
<span style="color:#555">{_e(adresse_club)}</span><br>
<span style="color:#555">{_e(' · '.join(x for x in (club.get('email'), club.get('telephone')) if x))}</span><br>
<span style="color:#555">{'Affiliation FFA n° ' + _e(club['numero_ffa']) if club.get('numero_ffa') else ''}</span></td>
<td align="right" valign="top"><span style="font-size:14pt;font-weight:bold">Reçu n° {_e(a.get('recu_numero'))}</span><br>
<span style="color:#555">établi le {date.today().strftime('%d/%m/%Y')}</span></td>
</tr></table>
<hr>
<p style="font-size:14pt;font-weight:bold;margin-top:18px">Reçu de cotisation {_e(a.get('saison'))}</p>
<p>Le club atteste avoir reçu de <b>{_e(a.get('prenom'))} {_e(a.get('nom'))}</b>
{('(né(e) le ' + _jour(a.get('date_naissance')) + ')') if a.get('date_naissance') else ''}
la somme de <b>{_euros(a.get('montant_paye'))}</b> pour son adhésion et sa licence de la saison {_e(a.get('saison'))}.</p>
<table style="margin-top:12px">{tableau}</table>
<p style="margin-top:40px">Pour le club,<br><b>{_e(club.get('president') or '')}</b></p>
<p style="color:#777;font-size:9pt;margin-top:60px">Reçu établi avec Trail Hub Center. Ce reçu atteste un paiement ;
il ne vaut pas reçu fiscal pour don.</p>
</div>"""


def rendre_recu(chemin, club, adhesion):
    pdf = QPdfWriter(str(chemin))
    pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                  QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter))
    pdf.setResolution(300)
    pdf.setTitle(f"Reçu {adhesion.get('recu_numero')}")
    doc = QTextDocument()
    doc.setHtml(html_recu(club, adhesion))
    doc.setPageSize(QSizeF(pdf.width(), pdf.height()))
    doc.print_(pdf)
    return chemin
