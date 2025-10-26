from __future__ import annotations

from typing import Any, Dict
import re
import html as htmllib


def clean_html_preserve_tables(text: str) -> str:
    """Enhanced HTML cleaning that preserves table structure and block formatting."""
    if not isinstance(text, str) or not text:
        return ""

    t = text

    # Preserve table semantics
    t = re.sub(r"<tr[^>]*>", "\n[ROW_START] ", t, flags=re.IGNORECASE)
    t = re.sub(r"</tr>", " [ROW_END]\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<td[^>]*>\s*</td>", " [EMPTY_CELL] ", t, flags=re.IGNORECASE)
    t = re.sub(r"<th[^>]*>\s*</th>", " [EMPTY_HEADER] ", t, flags=re.IGNORECASE)
    t = re.sub(r"<td[^>]*>", " [CELL] ", t, flags=re.IGNORECASE)
    t = re.sub(r"</td>", " [/CELL] ", t, flags=re.IGNORECASE)
    t = re.sub(r"<th[^>]*>", " [HEADER] ", t, flags=re.IGNORECASE)
    t = re.sub(r"</th>", " [/HEADER] ", t, flags=re.IGNORECASE)

    # Block-level spacing
    t = re.sub(r"</(h[1-6]|p|div)>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<br[^>]*/?>", "\n", t, flags=re.IGNORECASE)
    block_elements = [
        'div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'hr',
        'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'section', 'article', 'header', 'footer', 'nav', 'aside'
    ]
    for tag in block_elements:
        if tag.lower() not in {'h1','h2','h3','h4','h5','h6','p','div','br'}:
            t = re.sub(rf"</{tag}[^>]*>", " ", t, flags=re.IGNORECASE)

    # Strip remaining tags
    t = re.sub(r"<[^>]*>", "", t)

    # Decode entities
    t = htmllib.unescape(t)

    # Convert markers
    t = t.replace("[ROW_START]", "\n")
    t = t.replace("[ROW_END]", "")
    t = t.replace("[EMPTY_CELL]", "[Empty]")
    t = t.replace("[EMPTY_HEADER]", "[Empty Header]")
    t = t.replace("[CELL]", "")
    t = t.replace("[/CELL]", " | ")
    t = t.replace("[HEADER]", "")
    t = t.replace("[/HEADER]", " | ")

    # Normalize whitespace
    t = re.sub(r" +", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    t = "\n".join(line.strip() for line in t.splitlines())
    return t.strip()


def sanitize_section_obj(section: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(section, dict):
        return section
    if "sanitized_notes" in section:
        section["sanitized_notes"] = clean_html_preserve_tables(section.get("sanitized_notes", ""))
    if "notes" in section:
        section["sanitized_notes"] = clean_html_preserve_tables(section.get("notes", ""))
        section.pop("notes", None)
    # Recurse
    for k, v in list(section.items()):
        section[k] = sanitize_payload(v)
    return section


def sanitize_flatten_goods(value: Any) -> Any:
    """Sanitize the 'flatten_goods' structure by cleaning string fields recursively."""
    if isinstance(value, list):
        return [sanitize_flatten_goods(v) for v in value]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(v, str):
                out[k] = clean_html_preserve_tables(v)
            else:
                out[k] = sanitize_flatten_goods(v)
        return out
    return value


def sanitize_payload(data: Any):
    """Generic sanitizer: removes *.notes into sanitized_notes, cleans HTML in strings,
    preserves table semantics, recursively handles chapters, section, and flatten_goods.
    """
    if isinstance(data, list):
        return [sanitize_payload(item) for item in data]
    if isinstance(data, dict):
        working: Dict[str, Any] = dict(data)
        # Generic notes at this level (e.g., chapter.notes)
        if "notes" in working:
            working["sanitized_notes"] = clean_html_preserve_tables(working.get("notes", ""))
            working.pop("notes", None)

        out: Dict[str, Any] = {}
        for k, v in working.items():
            if k == "section" and isinstance(v, dict):
                out[k] = sanitize_section_obj(v)
            elif k == "chapters" and isinstance(v, list):
                out[k] = [sanitize_payload(ch) for ch in v]
            elif k == "flatten_goods":
                out[k] = sanitize_flatten_goods(v)
            elif isinstance(v, str):
                out[k] = clean_html_preserve_tables(v)
            else:
                out[k] = sanitize_payload(v)
        return out
    return data


