"""Indoor Plant and Pet Advisor API composition package."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from advisor_api.application import create_app

__all__ = ["create_app"]


def __getattr__(name: str) -> Any:
    """Load the app factory only when consumers explicitly request it.

    Keeping package initialization lightweight prevents migration and ingestion
    commands from constructing the entire web dependency graph.
    """

    if name == "create_app":
        from advisor_api.application import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
