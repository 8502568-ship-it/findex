"""Download plain-text Project Gutenberg books into data/gutenberg/.

Polite (delay between books) and tolerant: network hiccups are retried.
"""

import argparse
import http.client
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"


def fetch(book_id: int, retries: int = 3) -> bytes | None:
    """Return the book bytes, or None if it does not exist / keeps failing."""
    req = urllib.request.Request(
        URL.format(id=book_id), headers={"User-Agent": "findex-student-lab/1.0"}
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:  # no plain-text version of this book
                return None
            print(f"  {book_id}: HTTP {exc.code} (try {attempt}/{retries})")
        except (OSError, http.client.HTTPException) as exc:
            print(f"  {book_id}: {type(exc).__name__} (try {attempt}/{retries})")
        time.sleep(2 * attempt)  # back off before retrying
    return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("data/gutenberg"))
    p.add_argument("--count", type=int, default=200, help="books to have in total")
    p.add_argument("--start-id", type=int, default=1)
    p.add_argument("--delay", type=float, default=1.5, help="seconds between books")
    args = p.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    have = len(list(args.out.glob("*.txt")))
    book_id = args.start_id
    while have < args.count and book_id < args.start_id + args.count * 5:
        current = book_id
        book_id += 1
        target = args.out / f"pg{current}.txt"
        if target.exists():  # already downloaded on an earlier run
            continue
        data = fetch(current)
        if data is None:
            print(f"skip {current}")
        else:
            target.write_bytes(data)
            have += 1
            print(f"[{have}/{args.count}] {target.name}")
        time.sleep(args.delay)


if __name__ == "__main__":
    main()