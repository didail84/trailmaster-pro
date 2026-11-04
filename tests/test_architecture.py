"""Étape 1.3 — règles d'architecture de Trail Hub Center.

1. Le noyau ne dépend jamais de l'interface : aucun fichier de noyau/
   n'importe PySide6 ni interface/, même à l'intérieur d'une fonction.
2. Le noyau s'importe entièrement sur une machine sans PySide6.
3. Les anciens chemins (interface.coach, data.metriques…) donnent
   exactement le même module que le nouveau chemin du noyau.
4. La base de données ne dépend que des événements du noyau.
"""
import ast
import importlib
import pkgutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
INTERDITS_NOYAU = ("PySide6", "shiboken6", "interface")


def imports_du_fichier(chemin):
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield n.lineno, a.name
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            yield n.lineno, n.module


def test_le_noyau_n_importe_ni_pyside6_ni_l_interface():
    fautes = []
    for chemin in sorted((RACINE / "noyau").rglob("*.py")):
        for ligne, module in imports_du_fichier(chemin):
            if module.split(".")[0] in INTERDITS_NOYAU:
                fautes.append(f"{chemin.relative_to(RACINE)}:{ligne} importe {module}")
    assert not fautes, "\n".join(fautes)


def test_la_base_ne_depend_que_des_evenements_du_noyau():
    autorises = {"noyau.outils.evenements"}
    fautes = [f"ligne {l} : {m}" for l, m in imports_du_fichier(RACINE / "data" / "database.py")
              if m.split(".")[0] in ("interface", "noyau") and m not in autorises]
    assert not fautes, "\n".join(fautes)


def test_le_noyau_s_importe_sans_pyside6():
    script = textwrap.dedent("""
        import importlib, pkgutil, sys
        class Interdit:
            def find_spec(self, nom, *a, **k):
                if nom.split(".")[0] in ("PySide6", "shiboken6", "interface"):
                    raise ImportError("interdit dans le noyau : " + nom)
        sys.meta_path.insert(0, Interdit())
        import noyau
        noms = [m.name for m in pkgutil.walk_packages(noyau.__path__, "noyau.")]
        for n in noms:
            importlib.import_module(n)
        print(len(noms))
    """)
    r = subprocess.run([sys.executable, "-c", script], cwd=RACINE, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    assert int(r.stdout.strip()) >= 60


def relais():
    """(ancien chemin, nouveau chemin) de chaque relais de compatibilité."""
    couples = []
    for dossier in ("interface", "data"):
        for chemin in sorted((RACINE / dossier).glob("*.py")):
            texte = chemin.read_text(encoding="utf-8")
            if texte.startswith('"""Ancien emplacement de '):
                ligne = next(l for l in texte.splitlines() if l.startswith("from noyau."))
                paquet, nom = ligne.split()[1], ligne.split()[3]
                couples.append((f"{dossier}.{chemin.stem}", f"{paquet}.{nom}"))
    return couples


def test_il_y_a_bien_des_relais():
    assert len(relais()) == 58  # un relais par fichier déplacé à l'étape 1.3


@pytest.mark.parametrize("ancien, nouveau", relais())
def test_ancien_chemin_donne_le_meme_module(ancien, nouveau):
    assert importlib.import_module(ancien) is importlib.import_module(nouveau)


def test_evenement_vide_le_cache_du_coach():
    from noyau.entrainement import coach
    from noyau.outils.evenements import emettre, DONNEES_MODIFIEES
    coach._cache_acwr[999] = ("valeur", 0)
    emettre(DONNEES_MODIFIEES)
    assert 999 not in coach._cache_acwr


def test_un_abonne_en_erreur_ne_bloque_pas_les_autres():
    from noyau.outils import evenements as ev
    vus = []

    def casse(**_):
        raise RuntimeError("abonné défaillant")

    ev.abonner("essai", casse)
    ev.abonner("essai", lambda **k: vus.append(k))
    ev.emettre("essai", athlete_id=1)
    ev.desabonner("essai", casse)
    assert vus == [{"athlete_id": 1}]


def test_tout_le_logiciel_s_importe():
    erreurs = []
    for dossier in ("interface", "data", "noyau"):
        prefixe = dossier + "."
        if dossier == "noyau":
            import noyau
            noms = [m.name for m in pkgutil.walk_packages(noyau.__path__, prefixe)]
        else:
            noms = [prefixe + p.stem for p in (RACINE / dossier).glob("*.py") if p.stem != "__init__"]
        for nom in noms:
            try:
                importlib.import_module(nom)
            except Exception as e:  # pragma: no cover - message de diagnostic
                erreurs.append(f"{nom} : {e!r}")
    assert not erreurs, "\n".join(erreurs)
