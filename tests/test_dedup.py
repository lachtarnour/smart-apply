"""Tests for the dedup module."""

from __future__ import annotations

from dataclasses import dataclass

from smartapply.dedup import Deduplicator


@dataclass
class FakeJob:
    external_id: str
    title: str
    company: str
    description: str = ""


def test_deduplicator_groups_identical_jobs_across_sources() -> None:
    desc = "Build ML pipelines, deploy to AWS. PyTorch, Hugging Face."
    jobs = [
        FakeJob("serpapi:1", "Data Scientist H/F", "Acme SAS", desc),
        FakeJob("francetravail:1", "Data Scientist", "ACME", desc),
        FakeJob("manual:1", "ML Engineer", "Acme", "Different role focused on infra"),
    ]
    rep = Deduplicator().deduplicate(jobs)
    assert len(rep.unique) == 2
    assert len(rep.duplicate_groups) == 1
    assert {j.external_id for j in rep.duplicate_groups[0]} == {
        "serpapi:1",
        "francetravail:1",
    }


def test_deduplicator_keeps_distinct_companies_apart() -> None:
    jobs = [
        FakeJob("a", "Data Scientist", "Acme", "build pipelines"),
        FakeJob("b", "Data Scientist", "Beta", "build pipelines"),
    ]
    rep = Deduplicator().deduplicate(jobs)
    assert len(rep.unique) == 2
    assert rep.duplicate_groups == []


def test_dedup_report_counts_removed() -> None:
    desc = "pipeline pytorch"
    jobs = [
        FakeJob("a", "Data Scientist", "Acme", desc),
        FakeJob("b", "Data Scientist H/F", "Acme SAS", desc),
        FakeJob("c", "Data Scientist", "Acme Inc", desc),
        FakeJob("d", "ML Engineer", "Beta", "completely different"),
    ]
    rep = Deduplicator().deduplicate(jobs)
    assert len(rep.unique) == 2
    assert rep.n_duplicates_removed == 2
