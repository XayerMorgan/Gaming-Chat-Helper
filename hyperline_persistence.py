"""Safe local persistence and diagnostics for Hyperline.

This module intentionally depends only on the Python standard library so its
behavior can be tested without constructing the desktop UI.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from typing import Any


def atomic_write_json(
    path: str,
    data: Any,
    *,
    indent: int = 4,
    ensure_ascii: bool = True,
    trailing_newline: bool = False,
) -> None:
    """Serialize JSON beside *path*, then atomically replace the live file.

    Writing the temporary file in the destination directory keeps os.replace()
    on the same filesystem. If serialization or replacement fails, the
    previous file remains intact and the temporary file is removed.
    """
    destination = os.path.abspath(path)
    directory = os.path.dirname(destination)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{os.path.basename(destination)}.",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=indent, ensure_ascii=ensure_ascii)
            if trailing_newline:
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def configure_diagnostics(log_path: str) -> logging.Logger:
    """Return Hyperline's size-limited file logger without duplicate handlers."""
    logger = logging.getLogger("hyperline")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    absolute_log_path = os.path.abspath(log_path)
    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and os.path.abspath(handler.baseFilename) == absolute_log_path
        ):
            return logger

    try:
        handler = RotatingFileHandler(
            absolute_log_path,
            maxBytes=512 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
    except OSError:
        logger.addHandler(logging.NullHandler())
        return logger

    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger
