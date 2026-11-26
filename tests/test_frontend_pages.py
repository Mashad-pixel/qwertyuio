"""Static checks on student pages that have no server logic of their own."""
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def test_confirmation_page_has_well_formed_closing_tags():
    html = (FRONTEND / "student" / "confirmation.html").read_text(encoding="utf-8")
    assert "</bod</html>" not in html
    assert html.rstrip().endswith("</body></html>")
