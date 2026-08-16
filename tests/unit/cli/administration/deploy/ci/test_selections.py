from __future__ import annotations

import unittest
from typing import ClassVar

from cli.administration.deploy.ci import selections
from tests.utils.ci.job_names import deploy_job_name


def _job(name: str, conclusion: str | None, status: str = "completed") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


def _row(app: str, variant: str, mode: str, tor: bool = False) -> dict:
    return {
        "apps": app,
        "variant": variant,
        "mode": mode,
        "tor": "true" if tor else "false",
        "priority": "false",
    }


class TestResumeOffset(unittest.TestCase):
    """Where a retrigger picks the regular line up again."""

    _REGULAR: ClassVar[list[dict]] = [
        _row("web-app-a", "0", "compose"),
        _row("web-app-b", "1", "swarm", tor=True),
        _row("web-app-c", "0", "host"),
    ]

    def test_a_run_that_deployed_nothing_starts_at_the_head(self) -> None:
        self.assertEqual(selections.resume_offset(self._REGULAR, set()), "")

    def test_the_offset_is_the_last_row_of_the_leading_run(self) -> None:
        deployed = {"web-app-a#0@compose+clearnet", "web-app-b#1@swarm+tor"}
        self.assertEqual(
            selections.resume_offset(self._REGULAR, deployed), "web-app-b#1@swarm+tor"
        )

    def test_a_gap_stops_the_scan_rather_than_skipping_past_it(self) -> None:
        deployed = {"web-app-a#0@compose+clearnet", "web-app-c#0@host+clearnet"}
        self.assertEqual(
            selections.resume_offset(self._REGULAR, deployed),
            "web-app-a#0@compose+clearnet",
        )

    def test_a_run_that_covered_everything_resumes_at_the_last_row(self) -> None:
        deployed = {
            "web-app-a#0@compose+clearnet",
            "web-app-b#1@swarm+tor",
            "web-app-c#0@host+clearnet",
        }
        self.assertEqual(
            selections.resume_offset(self._REGULAR, deployed),
            "web-app-c#0@host+clearnet",
        )

    def test_the_verdict_does_not_matter_only_that_the_row_ran(self) -> None:
        jobs = [
            _job(deploy_job_name("swarm", "web-app-b", "1", tor=True), "failure"),
            _job(deploy_job_name("docker", "web-app-a", "0"), "success"),
        ]
        self.assertEqual(
            selections.deployed_selections(jobs),
            {"web-app-a#0@compose+clearnet", "web-app-b#1@swarm+tor"},
        )
