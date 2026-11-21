"""YAML design → DesignSubmission. No LLM involved: fast, exact, free.

The YAML comes from users, so it is treated as untrusted:
- size is capped before parsing,
- only plain data is allowed (`safe_load`, never `load`),
- YAML aliases (`*name`) are rejected: they can expand a tiny file into a huge structure
  (the "billion laughs" attack).
Every problem is reported with its location so the user can fix it.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml
from pydantic import ValidationError

from archoptimize.core.app_settings import get_app_settings
from archoptimize.core.errors import DesignInputError, InputIssue
from archoptimize.schemas.design_submission import DesignSubmission


class _NoAliasSafeLoader(yaml.SafeLoader):
    """SafeLoader that refuses YAML aliases."""

    def compose_node(self, parent, index):  # type: ignore[no-untyped-def]
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise yaml.composer.ComposerError(
                None, None, "YAML aliases (*name) are not allowed", event.start_mark
            )
        return super().compose_node(parent, index)


def _location(loc: tuple[int | str, ...]) -> str:
    """('design', 'components', 1, 'type') -> 'design.components[1].type'"""
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def _issues_from_validation(err: ValidationError) -> list[InputIssue]:
    return [
        InputIssue(location=_location(e["loc"]), message=e["msg"])
        for e in err.errors(include_url=False)
    ]


def parse_design_yaml(text: str) -> DesignSubmission:
    """Parse and validate a YAML design. Raises DesignInputError listing every problem."""
    limit = get_app_settings().max_design_chars
    if len(text) > limit:
        raise DesignInputError(
            [InputIssue("", f"input is {len(text):,} characters; the limit is {limit:,}")]
        )
    if not text.strip():
        raise DesignInputError([InputIssue("", "the input is empty")])

    try:
        data = yaml.load(text, Loader=_NoAliasSafeLoader)  # noqa: S506 (safe loader subclass)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise DesignInputError([InputIssue(where, f"invalid YAML: {problem}")]) from None

    if not isinstance(data, dict):
        raise DesignInputError(
            [InputIssue("", "expected a mapping with 'design' and 'requirements' keys")]
        )

    try:
        return DesignSubmission.model_validate(data)
    except ValidationError as err:
        raise DesignInputError(_issues_from_validation(err)) from None


def load_design_file(path: str | Path) -> DesignSubmission:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise DesignInputError([InputIssue("", "the file is not UTF-8 text")]) from None
    return parse_design_yaml(text)


def design_template_text() -> str:
    """The commented template shown to users (also a valid example design)."""
    return (
        resources.files("archoptimize.design_parsing")
        .joinpath("design_template.yaml")
        .read_text(encoding="utf-8")
    )
