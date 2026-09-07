"""Structural guard: every admin route that can spend money must be rate limited.

budget_service is the cap that actually bounds spend, but it reads *committed*
cost rows while the work runs async — so a burst can pass the cap before any of
it is billed. The limiter is what bounds that burst. This test fails when a new
LLM-triggering endpoint ships without one, which is easy to miss.

Discovery resolves imports rather than matching names: the handlers call
directly-imported functions (generate_deliverable, generate_toolkit_files,
run_content_analysis.delay), which a name regex cannot see.
"""
import ast
import pathlib

import pytest

_ROUTERS = pathlib.Path("app/api/v1")

# Service and worker modules that reach an LLM. Anything a router imports from
# one of these — or any of these imported as a module — means the handler spends.
_LLM_MODULES = {
    "assessment_service", "toolkit_service", "content_analysis_service",
    "content_brief_service", "content_roadmap_service", "deliverable_service",
    "citability_service", "misinformation_service", "report_service",
    "action_center_service", "claude_action", "scan_service",
    "content_tasks", "report_tasks", "scan_tasks",
}

# Verified by inspection as NOT reaching an LLM despite importing such a module:
#   create_or_rotate_share_token - mints a random share token
#   accept_assessment            - persists an admin decision on an existing row
#   send_report                  - emails an already-generated PDF
#   review / set_corrected /     - status transitions on an existing finding;
#   resolve                        imported from misinformation_service only
#                                  because `detect` lives in the same module
_VERIFIED_NON_SPENDING = {
    "create_or_rotate_share_token", "accept_assessment", "send_report",
    "review", "set_corrected", "resolve",
}


def _llm_names(tree: ast.AST) -> set[str]:
    """Names bound in this module that lead to an LLM call."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[-1]
            for alias in node.names:
                bound = alias.asname or alias.name
                # `from app.services.toolkit_service import generate_toolkit_files`
                # or `from app.services import toolkit_service`
                if mod in _LLM_MODULES or alias.name in _LLM_MODULES:
                    names.add(bound)
    return names


def _spending_routes():
    for path in sorted(_ROUTERS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in _VERIFIED_NON_SPENDING:
                continue
            decorators = [
                d for d in node.decorator_list
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr.upper() in ("POST", "PUT", "PATCH")
            ]
            if not decorators:
                continue
            # Imports can be module-level or inside the handler (this codebase
            # does both), so resolve names from the file AND the function body.
            names = _llm_names(tree) | _llm_names(node)
            used = {
                n.id for n in ast.walk(node) if isinstance(n, ast.Name)
            } | {
                n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
            }
            if names & used:
                yield path.name, node.name, ast.unparse(decorators[0])


_ROUTES = list(_spending_routes())


def test_spending_route_discovery_is_not_vacuous():
    # Guard the guard: if discovery breaks, the parametrized test would pass
    # by finding nothing. 9 routes are known to spend as of this commit.
    assert len(_ROUTES) >= 9, f"expected >=10 LLM routes, found {len(_ROUTES)}: {_ROUTES}"


@pytest.mark.parametrize(
    "fname,handler,decorator",
    [pytest.param(f, h, d, id=f"{f}::{h}") for f, h, d in _ROUTES],
)
def test_spending_route_is_rate_limited(fname, handler, decorator):
    assert "rate_limit" in decorator, (
        f"{fname}::{handler} can trigger an LLM call but has no rate limiter. "
        f"Add Depends(llm_generation_rate_limit) to its dependencies, or list it in "
        f"_VERIFIED_NON_SPENDING if it does not actually spend."
    )


def test_spending_routes_share_one_namespace():
    """A shared namespace means rotating between endpoints cannot sidestep the
    limit. Scans are deliberately separate — one costs ~100x a generation call."""
    from app.core import rate_limit as rl

    assert hasattr(rl, "llm_generation_rate_limit")
    for fname, handler, decorator in _ROUTES:
        limiter = "llm_generation_rate_limit" in decorator
        scan = "_scan_trigger_rate_limit" in decorator
        assert limiter or scan, f"{fname}::{handler} uses an unexpected limiter"
