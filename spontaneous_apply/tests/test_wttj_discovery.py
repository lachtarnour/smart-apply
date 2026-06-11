from __future__ import annotations

from spontaneous_apply.src.wttj_discovery import probable_wttj_slugs


def test_probable_wttj_slugs_normalizes_company_name() -> None:
    assert probable_wttj_slugs("Tandem Health") == ["tandem-health"]

