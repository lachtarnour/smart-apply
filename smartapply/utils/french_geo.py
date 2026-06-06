"""Backward-compatible shim for :mod:`smartapply.utils.geo.resolver`."""

from __future__ import annotations

import sys

from smartapply.utils.geo import resolver as _resolver

sys.modules[__name__] = _resolver
