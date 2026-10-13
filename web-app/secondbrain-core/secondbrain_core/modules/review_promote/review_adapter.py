"""Map the established Review frontmatter to the existing Knowledge schema."""
import re
from datetime import date


class ReviewFormatError(ValueError):
    pass


_FIELD = re.compile(r"^(type|status|review_status|captured_at|created|updated):\s*(.*?)\s*$")


def _date_prefix(value):
    match = re.match(r"^['\"]?(\d{4}-\d{2}-\d{2})", value)
    return match.group(1) if match else ""


def adapt_review_markdown(content, approved_at):
    """Return Knowledge Markdown, preserving all non-Review fields and body.

    The current Review contract uses type=review/status=pending. Existing
    Knowledge samples use type=knowledge/status=active and omit review_status.
    captured_at is retained; created is initialized from it and updated from
    the server approval date when those fields are absent.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewFormatError("Review item must be UTF-8 Markdown") from exc

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ReviewFormatError("Review frontmatter is required")
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if end is None:
        raise ReviewFormatError("Review frontmatter is unterminated")

    found = {}
    adapted = [lines[0]]
    for line in lines[1:end]:
        match = _FIELD.match(line.rstrip("\r\n"))
        if not match:
            adapted.append(line)
            continue
        key, value = match.groups()
        if key in found:
            raise ReviewFormatError("Duplicate Review frontmatter field: " + key)
        found[key] = value
        if key == "review_status":
            continue
        if key == "type":
            if value.strip("'\"") != "review":
                raise ReviewFormatError("Expected type: review")
            line = re.sub(r"^(type:\s*).*$", r"\1knowledge", line.rstrip("\r\n")) + ("\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else "")
        elif key == "status":
            if value.strip("'\"") != "pending":
                raise ReviewFormatError("Expected status: pending")
            line = re.sub(r"^(status:\s*).*$", r"\1active", line.rstrip("\r\n")) + ("\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else "")
        adapted.append(line)

    if "type" not in found or "status" not in found:
        raise ReviewFormatError("Review type and status fields are required")

    captured_date = _date_prefix(found.get("captured_at", ""))
    approved_date = _date_prefix(approved_at or "") or date.today().isoformat()
    if "created" not in found:
        adapted.append("created: " + (captured_date or approved_date) + "\n")
    if "updated" not in found:
        adapted.append("updated: " + approved_date + "\n")
    adapted.extend(lines[end:])
    return "".join(adapted).encode("utf-8")
