import asyncio
import json
import logging
import sys
import traceback
from pathlib import Path
from urllib.parse import urlsplit
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.live import Live
from rich.progress import Progress
from rich.table import Table

from findex.corpus import iter_documents
from findex.crawler import CrawlStats, crawl
from findex.index import InvertedIndex
from findex.parallel import DEFAULT_EXECUTOR, ExecutorKind, build_index, list_corpus

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


def _crawl_log_setup(log_file: Path) -> None:
    logger = logging.getLogger("findex.crawl")
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)


def _write_jsonl(path: Path, row: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


async def _crawl_command(
    seed_url: str,
    *,
    max_pages: int,
    concurrency: int,
    per_host: int,
    host_delay: float,
    out: Path,
    log_file: Path,
    allowed_domains: list[str] | None,
) -> CrawlStats:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    _crawl_log_setup(log_file)
    stats = CrawlStats()
    domains = set(allowed_domains or [])
    if not domains:
        domains = {urlsplit(seed_url).hostname or ""}

    table = Table(title="findex crawl")
    table.add_column("Pages", justify="right")
    table.add_column("Pages/s", justify="right")
    table.add_column("In flight", justify="right")
    table.add_column("Errors", justify="right")
    table.add_column("Queue", justify="right")

    def render() -> Table:
        table.rows.clear()
        table.add_row(
            str(stats.pages), f"{stats.pages_per_second:.2f}",
            str(stats.in_flight), str(stats.errors), str(stats.queue_depth),
        )
        return table

    with Live(render(), refresh_per_second=8, transient=False) as live:
        async for page in crawl(
            [seed_url],
            max_pages=max_pages,
            concurrency=concurrency,
            per_host=per_host,
            host_delay=host_delay,
            allowed_domains=domains,
            user_agent=(
                "findex-lab06/1.0 "
                "(+https://github.com/8502568-ship-it/findex)"
            ),
            stats=stats,
        ):
            await asyncio.to_thread(
                _write_jsonl,
                out,
                {
                    "url": page.url,
                    "title": page.title,
                    "text": page.text,
                    "fetched_at": page.fetched_at,
                    "status": page.status,
                    "bytes": page.num_bytes,
                },
            )
            live.update(render())
    return stats


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
    workers: Annotated[int, typer.Option("--workers", "-w", min=1, help="Number of workers")] = 1,
    executor: Annotated[
        ExecutorKind,
        typer.Option("--executor", help="How to run build_partial: serial, threads or processes"),
    ] = DEFAULT_EXECUTOR,
) -> None:
    """Build an inverted index from a directory of text files."""
    if not corpus_dir.exists():
        err_console.print(f"[red]Error:[/red] Corpus path '{corpus_dir}' does not exist.")
        raise typer.Exit(code=1)

    if corpus_dir.is_file() and corpus_dir.suffix.lower() == ".jsonl":
        idx = InvertedIndex()
        for doc in iter_documents(corpus_dir):
            idx.add_document(doc.doc_id, Path(doc.path).name, doc.text, positions)
        idx.save(out)
        console.print(f"[green]Successfully indexed {idx.total_docs} documents into {out}[/green]")
        return

    if not corpus_dir.is_dir():
        err_console.print(f"[red]Error:[/red] Corpus path '{corpus_dir}' is not a directory.")
        raise typer.Exit(code=1)

    paths = list_corpus(corpus_dir, limit)
    if not paths:
        err_console.print(f"[yellow]Warning:[/yellow] No .txt files found in '{corpus_dir}'.")
        raise typer.Exit(code=1)

    try:
        with Progress(transient=True) as progress:
            task = progress.add_task("Indexing documents...", total=None)

            def on_progress(done: int, total: int) -> None:
                progress.update(task, completed=done, total=total)

            idx, stats = build_index(
                paths,
                workers=workers,
                executor=executor,
                positions=positions,
                on_progress=on_progress,
            )
    except Exception:
        # Для processes у __cause__ лежить стек воркера (_RemoteTraceback).
        err_console.print("[red]Error:[/red] a worker failed, the build was aborted.")
        err_console.print(traceback.format_exc(), markup=False, highlight=False)
        raise typer.Exit(code=1)

    idx.save(out)
    console.print(f"[green]Successfully indexed {idx.total_docs} documents into {out}[/green]")
    err_console.print(
        f"[dim]{stats.executor} x{stats.workers}: wall {stats.wall_seconds:.2f}s, "
        f"cpu {stats.cpu_seconds:.2f}s, merge {stats.merge_seconds:.2f}s, "
        f"chunks {stats.chunks}[/dim]"
    )


@app.command("crawl")
def crawl_cmd(
    seed_url: Annotated[str, typer.Argument(help="Starting absolute HTTP(S) URL")],
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, help="Maximum pages to fetch")] = 500,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1, help="Number of async workers")] = 10,
    per_host: Annotated[int, typer.Option("--per-host", min=1, help="Maximum in-flight requests per host")] = 2,
    host_delay: Annotated[float, typer.Option("--host-delay", min=0.0, help="Minimum seconds between starts on one host")] = 0.1,
    out: Annotated[Path, typer.Option("--out", "-o", help="Streaming JSONL output")] = Path("data/crawl.jsonl"),
    log_file: Annotated[Path, typer.Option("--log-file", help="Per-URL crawl log")] = Path("crawl.log"),
    allowed_domain: Annotated[list[str] | None, typer.Option("--allowed-domain", help="Allowed host; repeat for multiple hosts")] = None,
) -> None:
    """Polite asyncio crawler; raw pages stream to JSONL for later indexing."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("", encoding="utf-8")
    try:
        stats = asyncio.run(
            _crawl_command(
                seed_url,
                max_pages=max_pages,
                concurrency=concurrency,
                per_host=per_host,
                host_delay=host_delay,
                out=out,
                log_file=log_file,
                allowed_domains=allowed_domain,
            ),
            debug=True,
        )
    except KeyboardInterrupt:
        err_console.print("[yellow]Crawl cancelled.[/yellow]")
        raise typer.Exit(code=130)
    except Exception as exc:
        err_console.print(f"[red]Crawl failed:[/red] {exc}")
        raise typer.Exit(code=1)
    console.print(
        f"[green]Crawled {stats.pages} pages[/green] -> {out}; "
        f"{stats.errors} errors; peak in-flight {stats.peak_in_flight}"
    )
    console.print(
        f"[dim]Index after crawl, outside the event loop: "
        f"findex index {out} -o index.json[/dim]"
    )


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
def serve(
    port: Annotated[int, typer.Option("--port", min=1, max=65535, help="HTTP port")] = 8000,
    workers: Annotated[int, typer.Option("--workers", min=1, help="Uvicorn worker processes")] = 1,
) -> None:
    """Run the FastAPI web search application with Uvicorn."""
    import uvicorn
    from findex.web.config import get_settings

    settings = get_settings()
    uvicorn.run("findex.web.app:app", host=settings.host, port=port, workers=workers, log_level=settings.log_level)


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