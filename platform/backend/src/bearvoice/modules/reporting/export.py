from pathlib import Path

from jinja2 import Environment, StrictUndefined

from bearvoice.modules.reporting.queries import DashboardSnapshot


TEMPLATE_PATH = Path(__file__).with_name("templates") / "kettle_report.md.j2"


def export_markdown(
    snapshot: DashboardSnapshot,
    destination: Path,
) -> Path:
    """Render a UTF-8 compatibility report from the canonical projection."""

    template = Environment(
        autoescape=False,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    ).from_string(TEMPLATE_PATH.read_text(encoding="utf-8"))
    rendered = template.render(snapshot=snapshot)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered.rstrip() + "\n", encoding="utf-8")
    return destination
