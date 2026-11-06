"""
Pages du jour de course (étape 6) sur le serveur :
  - /m/incident : fiche incident d'un bénévole. Sans réseau, le téléphone la garde (mémoire du navigateur) et
    l'envoie dès que le réseau revient, sans doublon ; en dernier recours, le numéro du PC course à appeler.
    C'est un outil d'organisation : en cas d'urgence vitale, on appelle le 15 ou le 112 d'abord ;
  - /m/commandement : le tableau de commandement sur téléphone (organisateur, bureau) ;
  - /m/poste-present : « je suis à mon poste » ;
  - /live/<jeton> : la page publique des proches (sans compte), coureurs et derniers pointages.
"""

import html
import json
from datetime import datetime

from noyau.donnees import comptes as dco
from noyau.serveur import web

JS_HORS_LIGNE = r"""
(function () {
  var CLE = 'thc_incidents_en_attente';
  function lire() { try { return JSON.parse(window.localStorage.getItem(CLE) || '[]'); } catch (e) { return []; } }
  function ecrire(l) { try { window.localStorage.setItem(CLE, JSON.stringify(l)); } catch (e) {} }
  function etat(t) { var z = document.getElementById('etat-envoi'); if (z) { z.innerHTML = t; z.style.display = t ? 'block' : 'none'; } }
  function corps(o) { var p = [], k; for (k in o) { if (o.hasOwnProperty(k)) { p.push(encodeURIComponent(k) + '=' + encodeURIComponent(o[k])); } } return p.join('&'); }
  function envoyer() {
    var l = lire();
    if (!l.length) { return; }
    var o = l[0], x = new XMLHttpRequest();
    x.open('POST', '/m/incident-envoi', true);
    x.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
    x.timeout = 15000;
    x.onload = function () {
      if (x.status === 200) {
        var r = {}; try { r = JSON.parse(x.responseText); } catch (e) {}
        l.shift(); ecrire(l);
        etat('✅ Incident n°' + (r.numero || '?') + ' reçu par le PC course.' + (l.length ? ' Encore ' + l.length + ' à envoyer…' : ''));
        if (l.length) { envoyer(); }
      } else if (x.status === 403 || x.status === 400) {
        etat('⚠️ Refusé par le serveur (' + x.status + ') : recharge la page et renvoie.');
      } else { attendre(l.length); }
    };
    x.onerror = x.ontimeout = function () { attendre(l.length); };
    x.send(corps(o));
  }
  function attendre(n) { etat('📵 Pas de réseau : ' + n + ' incident(s) gardé(s) sur ce téléphone, envoi automatique dès que le réseau revient. Ne ferme pas cette page.'); }
  function cle() { return 'i' + new Date().getTime().toString(36) + Math.random().toString(36).slice(2, 10); }
  var f = document.getElementById('form-incident');
  if (f) {
    f.onsubmit = function () {
      var o = {}, i, e;
      for (i = 0; i < f.elements.length; i++) { e = f.elements[i]; if (e.name) { o[e.name] = e.value; } }
      o.cle_client = cle(); o.horodatage = new Date(new Date().getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 19);
      var l = lire(); l.push(o); ecrire(l);
      f.reset(); etat('Envoi…'); envoyer(); return false;
    };
  }
  window.addEventListener('online', envoyer);
  setInterval(envoyer, 30000);
  if (lire().length) { attendre(lire().length); envoyer(); }
})();
"""


def _e(v):
    return html.escape("" if v is None else str(v))


def _evenement(handler, compte, q, page_code):
    ev = int(q.get("ev") or 0) if str(q.get("ev") or "").isdigit() else 0
    if not web.peut_evenement(compte, page_code, ev):
        handler._refus(compte)
        return None
    return ev


# ------------------------------------------------------------------ incident

def page_incident(compte, csrf, evenement_id, message=None, classe="ok"):
    from noyau.donnees import organisation as dor, commandement as dk
    from noyau.organisation import commandement as K
    ev = dor.evenement(evenement_id)
    r = dk.reglages_live(evenement_id) or {}
    pts = dk.points(evenement_id)
    opts = lambda paires, defaut=None: "".join(f"<option value='{_e(k)}'{' selected' if k == defaut else ''}>{_e(l)}</option>"
                                               for k, l in paires)
    tel = r.get("pc_telephone")
    m = f"<div class='carte {classe}'>{message}</div>" if message else ""
    return web.page(f"Incident · {ev['nom']}", m + f"""<div class='carte err'><b>Urgence vitale : appelle d'abord le 15 ou le 112</b>,
puis fais la fiche.</div><div id='etat-envoi' class='carte att' style='display:none'></div>
<form id='form-incident' method='post' action='/m/incident?ev={evenement_id}' class='carte'>{web._champ_csrf(csrf)}
<input type='hidden' name='ev' value='{evenement_id}'>
<label>Gravité</label><select name='gravite'>{opts(K.GRAVITES, 'moyen')}</select>
<label>Type</label><select name='type'>{opts(K.TYPES_INCIDENT, 'blessure')}</select>
<label>Dossard (si un coureur est concerné)</label><input name='dossard' inputmode='numeric' pattern='[0-9]*'>
<label>Où</label><select name='point_id'><option value=''>— sur le parcours —</option>{opts([(p['id'], p['nom'] + (' · km ' + format(p['km'], 'g') if p.get('km') else '')) for p in pts])}</select>
<label>Kilomètre (environ)</label><input name='km' inputmode='decimal'>
<label>Ce qui se passe</label><input name='description' maxlength='500'>
<button type='submit'>Envoyer au PC course</button></form>
{f"<p>Sans réseau du tout : <a href='tel:{_e(tel)}'>appeler le PC course ({_e(tel)})</a> · <a href='sms:{_e(tel)}'>SMS</a></p>" if tel else ""}
<p class='petit'>Sans réseau, la fiche reste sur ce téléphone et part toute seule quand le réseau revient (garde cette page ouverte).</p>
<script src='/m/hors-ligne.js'></script>""", compte)


def gerer_incident(handler, compte, csrf, verbe, chemin, q, f):
    from noyau.donnees import commandement as dk
    if chemin == "/m/hors-ligne.js":
        return handler._envoyer(200, JS_HORS_LIGNE, "application/javascript; charset=utf-8")
    if chemin == "/m/incident-envoi":                      # envoi d'un téléphone (aussi après une coupure de réseau)
        if verbe != "POST":
            return handler._envoyer(405, "{}", "application/json")
        ev = int(f.get("ev") or 0) if str(f.get("ev") or "").isdigit() else 0
        if not web.peut_evenement(compte, "incident", ev):
            return handler._envoyer(403, json.dumps({"erreur": "refus"}), "application/json")
        try:
            iid, cree = dk.signaler(ev, f, compte.get("nom_affiche") or compte["identifiant"], compte["id"])
        except dk.ErreurCommandement as e:
            return handler._envoyer(400, json.dumps({"erreur": str(e)}), "application/json")
        if cree:
            dco.journaliser(compte["id"], compte["identifiant"], "ecriture", "web.incident", detail=f"ev {ev} incident {iid}",
                            adresse=handler._ip())
        n = next((i["numero"] for i in dk.incidents(ev) if i["id"] == iid), None)
        return handler._envoyer(200, json.dumps({"ok": True, "numero": n, "deja": not cree}), "application/json")
    ev = _evenement(handler, compte, q, "incident")
    if ev is None:
        return None
    if verbe == "POST":
        try:
            iid, _c = dk.signaler(ev, f, compte.get("nom_affiche") or compte["identifiant"], compte["id"])
        except dk.ErreurCommandement as e:
            return handler._envoyer(200, page_incident(compte, csrf, ev, _e(e), "err"))
        dco.journaliser(compte["id"], compte["identifiant"], "ecriture", "web.incident", detail=f"ev {ev} incident {iid}",
                        adresse=handler._ip())
        n = next((i["numero"] for i in dk.incidents(ev) if i["id"] == iid), "?")
        return handler._envoyer(200, page_incident(compte, csrf, ev, f"✅ Incident n°{n} reçu par le PC course."))
    return handler._envoyer(200, page_incident(compte, csrf, ev))


# ------------------------------------------------------------------ tableau de commandement (téléphone)

def page_commandement(compte, csrf, evenement_id, message=None):
    from noyau.donnees import organisation as dor, commandement as dk
    ev = dor.evenement(evenement_id)
    t = dk.tableau(evenement_id)
    b = t["bilan"]
    m = f"<div class='carte ok'>{message}</div>" if message else ""
    inc = "".join(
        f"<div class='carte {'err' if i['gravite'] == 'urgent' else 'att'}'><b>n°{i['numero']} · {_e(i['libelle_gravite'])} · "
        f"{_e(i['libelle_type'])}</b><br>{_e(i['horodatage'][11:16])} · {_e(i['point'] or ('km ' + format(i['km'], 'g') if i['km'] else ''))}"
        f"{' · dossard ' + str(i['dossard']) + ' ' + _e(i['coureur']) if i['dossard'] else ''}<br>{_e(i['description'] or '')}"
        f"<br><span class='petit'>{_e('pris en charge par ' + i['pris_par'] if i['pris_par'] else 'signalé par ' + (i['signale_par'] or ''))}</span>"
        f"<form method='post' action='/m/commandement?ev={evenement_id}'>{web._champ_csrf(csrf)}<input type='hidden' name='incident' value='{i['id']}'>"
        f"<div class='ligne'><button name='action' value='prendre' class='second'>Je m'en occupe</button>"
        f"<button name='action' value='clore'>Clore</button></div></form></div>"
        for i in t["incidents_ouverts"])
    al = "".join(f"<tr><td><b>{l['dossard']}</b></td><td>{_e(l['nom'])}<br><span class='petit'>{_e(l['alerte'])}</span></td></tr>"
                 for l in t["alertes"][:25])
    postes = "".join(f"<tr><td>{_e(p['poste'])}</td><td class='droite'>{p['presents']}/{p['affectes']}</td></tr>"
                     for p in t["postes"] if p["affectes"])
    return web.page(f"PC course · {ev['nom']}", m + f"""<div class='carte'><table>
<tr><td>En course</td><td class='droite'><b>{b['en_course']}</b></td></tr><tr><td>À chercher (pas vus au point suivant)</td><td class='droite'><b>{b['a_chercher']}</b></td></tr>
<tr><td>Hors délai</td><td class='droite'>{b['hors_delai']}</td></tr><tr><td>Arrivés</td><td class='droite'>{b['arrives']}</td></tr>
<tr><td>Abandons</td><td class='droite'>{b['abandons']}</td></tr><tr><td>Bénévoles à leur poste</td><td class='droite'>{t['benevoles_presents']}/{t['benevoles_attendus']}</td></tr></table></div>
<h2>Incidents ouverts ({len(t['incidents_ouverts'])})</h2>{inc or "<p class='petit'>Aucun.</p>"}
<h2>Coureurs à surveiller</h2><div class='carte'><table>{al or "<tr><td class='petit'>Personne.</td></tr>"}</table></div>
<h2>Postes</h2><div class='carte'><table>{postes or "<tr><td class='petit'>Pas de bénévoles affectés.</td></tr>"}</table></div>
<p class='petit'>Mis à jour à {datetime.now():%H:%M:%S}. Recharge la page pour actualiser.</p>""", compte)


def gerer_commandement(handler, compte, csrf, verbe, chemin, q, f):
    from noyau.donnees import commandement as dk
    ev = _evenement(handler, compte, q, "commandement")
    if ev is None:
        return None
    msg = None
    if verbe == "POST" and str(f.get("incident") or "").isdigit():
        iid = int(f["incident"])
        if not any(i["id"] == iid for i in dk.incidents(ev)):
            return handler._refus(compte)
        par = compte.get("nom_affiche") or compte["identifiant"]
        if f.get("action") == "clore":
            dk.clore(iid, par)
            msg = "Incident clos."
        else:
            dk.prendre_en_charge(iid, par)
            msg = "Tu t'occupes de l'incident."
        dco.journaliser(compte["id"], compte["identifiant"], "ecriture", "web.incident.suivi",
                        detail=f"incident {iid} {f.get('action')}", adresse=handler._ip())
    return handler._envoyer(200, page_commandement(compte, csrf, ev, msg))


# ------------------------------------------------------------------ présence au poste

def gerer_presence(handler, compte, csrf, verbe, chemin, q, f):
    from noyau.donnees import commandement as dk, logistique as dl
    ev = _evenement(handler, compte, q, "poste")
    if ev is None:
        return None
    if verbe == "POST" and str(f.get("poste") or "").isdigit():
        mien = [b for b in dl.benevoles(ev) if compte.get("personne_id") and b["personne_id"] == compte["personne_id"]]
        if mien:
            try:
                dk.marquer_present(int(f["poste"]), mien[0]["id"], f.get("present", "1") == "1")
                dco.journaliser(compte["id"], compte["identifiant"], "ecriture", "web.presence", detail=f"poste {f['poste']}",
                                adresse=handler._ip())
            except dk.ErreurCommandement:
                pass
    return handler._rediriger(f"/m/poste?ev={ev}")


PAGES = {"/m/incident": gerer_incident, "/m/hors-ligne.js": gerer_incident, "/m/commandement": gerer_commandement,
         "/m/poste-present": gerer_presence}


# ------------------------------------------------------------------ page publique

def page_publique(handler, jeton, q):
    from noyau.donnees import commandement as dk, organisation as dor
    ev_id = dk.evenement_du_jeton(jeton)
    if not ev_id:
        return handler._envoyer(404, web.page("Suivi en direct", "<div class='carte err'>Ce suivi n'existe pas ou n'est plus "
                                                                 "ouvert.</div>"))
    ev = dor.evenement(ev_id)
    rech = (q.get("q") or "")[:40]
    lignes = dk.suivi_public(ev_id, rech)
    corps = "".join(f"<tr><td><b>{l['dossard']}</b></td><td>{_e(l['nom'])}<br><span class='petit'>{_e(l['epreuve'])}</span></td>"
                    f"<td>{_e(l['etat'])}<br><span class='petit'>{_e(l['dernier'])} {_e(l['heure'])}</span></td>"
                    f"<td class='droite'>{_e(l['temps'] or l['arrivee_estimee'] and '≈ ' + l['arrivee_estimee'])}</td></tr>"
                    for l in lignes[:300])
    contenu = (f"<form method='get' class='carte'><label>Chercher un coureur (nom ou dossard)</label><input name='q' value='{_e(rech)}'>"
               f"<button type='submit'>Chercher</button></form><div class='carte'><table>"
               f"<tr><td class='petit'>Dos.</td><td class='petit'>Coureur</td><td class='petit'>Où</td><td class='petit droite'>Temps · arrivée</td></tr>"
               f"{corps or '<tr><td>Personne.</td></tr>'}</table></div>"
               f"<p class='petit'>Derniers pointages aux points de contrôle ; l'heure d'arrivée est une estimation. Mis à jour à "
               f"{datetime.now():%H:%M}. Page actualisée toute seule chaque minute.</p>")
    p = web.page(f"En direct · {ev['nom']}", contenu).replace("<meta name='color-scheme'",
                                                             "<meta http-equiv='refresh' content='60'><meta name='color-scheme'")
    return handler._envoyer(200, p)
