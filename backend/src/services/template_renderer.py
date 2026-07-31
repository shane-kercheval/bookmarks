"""
Jinja2 template rendering with strict validation.

Renders prompt templates with user-provided arguments,
validating that required arguments are present and
rejecting unknown arguments.
"""

import logging
from typing import Any

from jinja2 import StrictUndefined, TemplateSyntaxError, UndefinedError
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

logger = logging.getLogger(__name__)


class TemplateError(Exception):
    """Raised when template rendering fails."""

    pass


# Sandboxed Jinja2 environment: blocks unsafe attribute access (the attribute
# traversal that server-side template injection relies on) while keeping strict
# undefined-variable handling. Prompt content is user-authored and untrusted, so
# a plain Environment is NOT a safe boundary here — only SandboxedEnvironment is.
_jinja_env = SandboxedEnvironment(undefined=StrictUndefined)


def render_template(
    content: str | None,
    arguments: dict[str, Any] | None,
    defined_args: list[dict[str, Any]],
) -> str:
    """
    Render a Jinja2 template with argument validation.

    Args:
        content: The Jinja2 template content. Returns empty string if None.
        arguments: User-provided argument values. Keys are argument names.
        defined_args: List of argument definitions from the prompt.
            Each dict has 'name', 'description', and 'required' keys.

    Returns:
        The rendered template string.

    Raises:
        TemplateError: If required arguments are missing, unknown arguments
            are provided, or template rendering fails.
    """
    if not content:
        return ""

    arguments = arguments or {}

    # Build set of defined argument names
    defined_names = {arg["name"] for arg in defined_args}

    # Check for unknown arguments
    unknown = set(arguments.keys()) - defined_names
    if unknown:
        raise TemplateError(
            f"Unknown argument(s): {', '.join(sorted(unknown))}. "
            f"Valid arguments: {', '.join(sorted(defined_names)) if defined_names else 'none'}",
        )

    # Check for missing required arguments
    required_names = {
        arg["name"] for arg in defined_args if arg.get("required") is True
    }
    missing = required_names - set(arguments.keys())
    if missing:
        raise TemplateError(
            f"Missing required argument(s): {', '.join(sorted(missing))}",
        )

    # Provide default empty string for optional arguments not provided
    # This allows {% if var %} conditions to work correctly with StrictUndefined
    render_args = dict(arguments)
    for arg in defined_args:
        if arg["name"] not in render_args:
            render_args[arg["name"]] = ""

    # Render template
    try:
        template = _jinja_env.from_string(content)
        return template.render(**render_args)
    except TemplateSyntaxError as e:
        raise TemplateError(f"Template syntax error: {e.message}") from e
    except UndefinedError as e:
        raise TemplateError(f"Template variable error: {e}") from e
    except SecurityError as e:
        # The sandbox blocked an unsafe operation (e.g. the attribute traversal
        # used in server-side template injection). Log full detail server-side for
        # attack detection and false-positive triage; return a generic message to
        # the caller so we don't echo the offending expression back. Mirrors the
        # decode_clerk_jwt pattern in core/auth.py (detail logged, generic to client).
        # Per-caller prompt_id/user_id logging is deliberately deferred: this branch
        # collapses SecurityError into the generic TemplateError, so callers can't
        # distinguish a security block from a benign template error without a
        # dedicated TemplateSecurityError subclass (tracked as a follow-up).
        logger.warning("Blocked sandboxed template render: %s", e, exc_info=True)
        raise TemplateError("Template uses a disallowed operation.") from e
