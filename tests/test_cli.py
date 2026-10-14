import pytest
from typer.testing import CliRunner

from copernicus.cli import app
from copernicus.sites import Site

runner = CliRunner()


class TestSites:
    def test_lists_every_site(self):
        result = runner.invoke(app, ["sites"])
        assert result.exit_code == 0
        for site in Site:
            assert site.value in result.output


class TestLink:
    def test_prints_a_browser_url(self):
        result = runner.invoke(app, ["link", "tanneron", "--date", "2026-02-17"])
        assert result.exit_code == 0
        assert result.output.startswith("https://browser.dataspace.copernicus.eu/?")

    def test_rejects_a_malformed_date(self):
        result = runner.invoke(app, ["link", "tanneron", "--date", "17/02/2026"])
        assert result.exit_code != 0

    def test_rejects_two_period_scripts(self):
        result = runner.invoke(
            app,
            ["link", "tanneron", "--date", "2026-02-17", "-s", "mimosa"],
            env={"COLUMNS": "200"},
        )
        assert result.exit_code != 0
        assert "single-period" in result.output


class TestRender:
    # Every case fails on arguments, before any credential or network access.
    @pytest.mark.parametrize(
        ("script", "periods", "hint"),
        [
            ("mimosa", ["bloom=2026-01-20..2026-03-10"], "base=FROM..TO"),
            ("burn_severity", ["2025-07-10..2025-08-04"], "pre=FROM..TO"),
            ("true_color", ["x=2026-02-17"], "--period FROM..TO"),
            ("true_color", ["2026-02-30"], "day is out of range"),
        ],
    )
    def test_checks_periods_against_the_script(self, script, periods, hint):
        args = ["render", "tanneron", "-o", "x.png", "-s", script]
        for period in periods:
            args += ["--period", period]
        result = runner.invoke(app, args, env={"COLUMNS": "200"})
        assert result.exit_code == 2
        assert hint in result.output


class TestStandCommands:
    # Both fail on arguments, before any credential or network access.
    @pytest.mark.parametrize(
        "args",
        [
            ["series", "aude_2025", "-p", "2025-08-01..2025-09-01"],
            ["frames", "aude_2025", "-d", "2025-08-20=après"],
        ],
    )
    def test_fire_sites_have_no_stand_signal(self, args):
        result = runner.invoke(app, args, env={"COLUMNS": "200"})
        assert result.exit_code == 2
        assert "no stand-level signal" in result.output

    def test_rejects_a_bad_base_period(self):
        args = ["frames", "ceillac", "-d", "2025-10-15=début", "--base", "2025-13-01"]
        result = runner.invoke(app, args, env={"COLUMNS": "200"})
        assert result.exit_code == 2
        assert "month must be in 1..12" in result.output
