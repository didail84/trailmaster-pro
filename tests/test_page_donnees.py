"""La page Claude embarque les mêmes données que le logiciel (nutrition, matériel obligatoire)."""
import importlib.util
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def test_donnees_de_la_page_a_jour():
    spec = importlib.util.spec_from_file_location("gen", RACINE / "page_claude" / "generer_donnees_page.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    page = (RACINE / "page_claude" / "trail_hub_center.html").read_text(encoding="utf-8")
    for nom in gen.REPERES:
        assert gen.bloc(nom) in page, "Lance python page_claude/generer_donnees_page.py"
