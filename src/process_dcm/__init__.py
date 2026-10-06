"""Top-level package for Process DCM."""

from importlib import metadata

try:
    __version__ = metadata.version(__name__)
except metadata.PackageNotFoundError:  # no cov
    __version__ = "0.0.0.dev0"
