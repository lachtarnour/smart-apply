"""Tests for the dedup module."""

from __future__ import annotations

from dataclasses import dataclass

from smartapply.dedup import Deduplicator, normalize_company, normalize_title


@dataclass
class FakeJob:
    external_id: str
    title: str
    company: str
    description: str = ""


def test_normalize_company_strips_suffixes_and_accents() -> None:
    assert normalize_company("Acme SAS") == "acme"
    assert normalize_company("Acme S.A.S.") == "acme"
    assert normalize_company("Acme Inc.") == "acme"
    assert normalize_company("Société Générale") == "societe generale"


def test_normalize_title_strips_hf_and_contract() -> None:
    assert normalize_title("Data Scientist H/F") == "data scientist"
    assert normalize_title("Senior Data Scientist CDI") == "data scientist"


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


def test_deduplicator_thresholds_configurable() -> None:
    jobs = [
        FakeJob(
            "a",
            "Senior Data Scientist",
            "Acme",
            "Build ML pipelines using PyTorch and deploy on AWS.",
        ),
        FakeJob(
            "b",
            "Data Scientist Senior",
            "Acme",
            "Develop deep learning models with TensorFlow on Kubernetes.",
        ),
    ]
    strict = Deduplicator(title_threshold=99, desc_threshold=99).deduplicate(jobs)
    lax = Deduplicator(title_threshold=70, desc_threshold=20).deduplicate(jobs)
    assert len(strict.unique) == 2
    assert len(lax.unique) == 1


def test_deduplicator_no_description_falls_back_to_title() -> None:
    jobs = [
        FakeJob("a", "Data Scientist", "Acme", ""),
        FakeJob("b", "Data Scientist", "Acme", ""),
    ]
    rep = Deduplicator().deduplicate(jobs)
    assert len(rep.unique) == 1


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
