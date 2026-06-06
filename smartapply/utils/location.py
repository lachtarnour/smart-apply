"""Backward-compatible shim for :mod:`smartapply.utils.geo.validation`."""

from __future__ import annotations

import sys

from smartapply.utils.geo import validation as _validation

sys.modules[__name__] = _validation
