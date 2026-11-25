"""code-factory: a harness that drives Claude coding agents from task to pull request."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("code-factory")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"

__all__ = ["__version__"]
