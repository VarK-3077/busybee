"""The export-pdf command: clear error without Chromium, correct print call with it."""

from pathlib import Path

from typer.testing import CliRunner

from busybee import cli

runner = CliRunner()


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "out"
    bundle.mkdir()
    (bundle / "index.html").write_text("<html></html>", encoding="utf-8")
    return bundle


def test_export_pdf_reports_missing_chromium(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "find_chromium", lambda: None)
    arguments = ["export-pdf", "--bundle", str(_bundle(tmp_path)), "--out", str(tmp_path / "r.pdf")]
    result = runner.invoke(cli.app, arguments)
    assert result.exit_code == 1
    assert "Chromium" in result.output


def test_export_pdf_runs_headless_print(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(next(c for c in command if c.startswith("--print-to-pdf="))[15:]).write_bytes(b"%PDF")

        class Done:
            returncode = 0
            stderr = ""

        return Done()

    monkeypatch.setattr(cli, "find_chromium", lambda: "chromium")
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    out = tmp_path / "sub" / "r.pdf"
    result = runner.invoke(
        cli.app, ["export-pdf", "--bundle", str(_bundle(tmp_path)), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "--no-pdf-header-footer" in calls[0] and calls[0][-1].endswith("index.html")
