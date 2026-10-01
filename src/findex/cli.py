import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table

from findex.index import InvertedIndex

app = typer.Typer(help="findex: Modern Search Engine CLI")
console = Console()
err_console = Console(stderr=True)


def setup_logging(verbose: int) -> None:
    if verbose == 0:
        level = logging.WARNING
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


@app.callback()
def main(
    verbose: Annotated[
        int,
        typer.Option("-v", "--verbose", count=True, help="Increase verbosity (-v for INFO, -vv for DEBUG)"),
    ] = 0,
) -> None:
    """Global CLI options."""
    setup_logging(verbose)


@app.command()
def index(
    corpus_dir: Annotated[Path, typer.Argument(help="Path to folder with text documents")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output index JSON file")] = Path("index.json"),
    positions: Annotated[bool, typer.Option("--positions", help="Store token positions")] = False,
    limit: Annotated[int | None, typer.Option("--limit", help="Limit number of docs to index")] = None,
) -> None:
    """Build an inverted index from a directory of text files."""
    if not corpus_dir.exists() or not corpus_dir.is_dir():
        err_console.print(f"[red]Error:[/red] Corpus directory '{corpus_dir}' does not exist.")
        raise typer.Exit(code=1)

    files = sorted(list(corpus_dir.glob("*.txt")))
    if limit is not None:
        files = files[:limit]

    if not files:
        err_console.print(f"[yellow]Warning:[/yellow] No .txt files found in '{corpus_dir}'.")
        raise typer.Exit(code=1)

    idx = InvertedIndex()
    for doc_id, file_path in enumerate(track(files, description="Indexing documents...")):
        try:
            content = file_path.read_text(encoding="utf-8")
            idx.add_document(doc_id=doc_id, title=file_path.name, text=content, store_positions=positions)
        except Exception as e:
            logging.getLogger(__name__).warning("Failed to read %s: %s", file_path, e)

    idx.save(out)
    console.print(f"[green]Successfully indexed {idx.total_docs} documents into {out}[/green]")


@app.command()
def search(
    index_file: Annotated[Path, typer.Argument(help="Path to the saved index JSON file")],
    query: Annotated[str, typer.Argument(help="Search query")],
    k: Annotated[int, typer.Option("--k", help="Number of results to return")] = 10,
    scorer: Annotated[Literal["bm25", "tfidf"], typer.Option("--scorer", help="Ranking scorer")] = "bm25",
    as_json: Annotated[bool, typer.Option("--json", help="Emit raw JSON lines to stdout")] = False,
) -> None:
    """Search an index for a query with BM25 or TF-IDF ranking."""
    try:
        idx = InvertedIndex.load(index_file)
    except FileNotFoundError:
        err_console.print(f"[red]Error:[/red] Index file '{index_file}' does not exist.")
        raise typer.Exit(code=1)
    except Exception as e:
        err_console.print(f"[red]Error loading index:[/red] {e}")
        raise typer.Exit(code=1)

    results = idx.search(query=query, k=k, scorer_name=scorer)

    if as_json:
        for r in results:
            print(json.dumps({"doc_id": r.doc_id, "score": round(r.score, 4), "title": r.title}))
        return

    table = Table(title=f"Search Results for: '{query}' (Scorer: {scorer.upper()})")
    table.add_column("Rank", justify="right", style="cyan")
    table.add_column("Doc ID", justify="right", style="magenta")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Title", style="white")

    for rank, r in enumerate(results, start=1):
        table.add_row(str(rank), str(r.doc_id), f"{r.score:.4f}", r.title)

    console.print(table)


@app.command()
def stats(
    index_file: Annotated[Path, typer.Argument(help="Path to the saved index JSON file")],
) -> None:
    """Print statistical overview of the index."""
    try:
        idx = InvertedIndex.load(index_file)
    except FileNotFoundError:
        err_console.print(f"[red]Error:[/red] Index file '{index_file}' does not exist.")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Total Documents:[/bold cyan] {idx.total_docs}")
    console.print(f"[bold cyan]Unique Terms:[/bold cyan] {len(idx.postings)}")
    console.print(f"[bold cyan]Average Doc Length:[/bold cyan] {idx.avg_doc_len:.2f}")


if __name__ == "__main__":
    app()