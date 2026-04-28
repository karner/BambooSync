"""
Logging utility.

Component Type: Utility (Cross-cutting).
Wraps stdlib logging with a consistent format. Callable by any layer.
"""

import logging
import sys

_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
_DATE   = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format=_FORMAT,
    datefmt=_DATE,
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
