import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def render_advisory(text: str) -> str:
    """Renders the small markdown subset used in ml/advisory_rag knowledge
    base entries (headers, **bold**, - bullets) as HTML. Deliberately
    minimal -- not a general markdown parser -- since the input is only
    ever our own generated/template advisory text, never arbitrary user input."""
    if not text:
        return ""

    lines = text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("- "):
            if not in_list:
                html_parts.append('<ul class="list-disc pl-5 space-y-1">')
                in_list = True
            html_parts.append(f"<li>{_inline(stripped[2:])}</li>")
            continue

        if in_list:
            html_parts.append("</ul>")
            in_list = False

        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
            html_parts.append(f'<p class="font-serif text-lg font-semibold mt-3">{_inline(stripped)}</p>')
        else:
            html_parts.append(f'<p class="mt-2">{_inline(stripped)}</p>')

    if in_list:
        html_parts.append("</ul>")

    return mark_safe("".join(html_parts))


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return text
