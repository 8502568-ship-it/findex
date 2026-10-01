import json
from pathlib import Path

from typer.testing import CliRunner

from findex.cli import app

runner = CliRunner()

def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "findex" in result.stdout

def test_cli_index_command(small_corpus: Path, tmp_path: Path):
    out_file = tmp_path / "idx.json"
    result = runner.invoke(app, ["index", str(small_corpus), "--out", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()

def test_cli_stats_command(small_corpus: Path, tmp_path: Path):
    out_file = tmp_path / "idx.json"
    runner.invoke(app, ["index", str(small_corpus), "--out", str(out_file)])
    result = runner.invoke(app, ["stats", str(out_file)])
    assert result.exit_code == 0
    assert "Total Documents: 3" in result.stdout

def test_cli_search_table(small_corpus: Path, tmp_path: Path):
    out_file = tmp_path / "idx.json"
    runner.invoke(app, ["index", str(small_corpus), "--out", str(out_file)])
    result = runner.invoke(app, ["search", str(out_file), "fox"])
    assert result.exit_code == 0
    assert "Rank" in result.stdout

def test_cli_search_json_output(small_corpus: Path, tmp_path: Path):
    out_file = tmp_path / "idx.json"
    runner.invoke(app, ["index", str(small_corpus), "--out", str(out_file)])
    result = runner.invoke(app, ["search", str(out_file), "fox", "--json"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.strip().split("\n") if line]
    data = json.loads(lines[0])
    assert "doc_id" in data
    assert "score" in data

def test_cli_nonexistent_file_exits_nonzero(tmp_path: Path):
    result = runner.invoke(app, ["search", str(tmp_path / "ghost.json"), "query"])
    assert result.exit_code == 1
    assert "Error:" in result.stderr