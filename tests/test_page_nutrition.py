"""La page Claude embarque les mêmes données de nutrition que le logiciel (barèmes, ingrédients, recettes)."""
import importlib.util
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def test_donnees_nutrition_de_la_page_a_jour():
    spec = importlib.util.spec_from_file_location("gen", RACINE / "page_claude" / "generer_donnees_nutrition.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    page = (RACINE / "page_claude" / "trail_hub_center.html").read_text(encoding="utf-8")
    assert gen.bloc() in page, "Lance python page_claude/generer_donnees_nutrition.py"
