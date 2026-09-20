"""Download plain-text Project Gutenberg books into data/gutenberg/ (polite: 1 req/s)."""

import argparse
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("data/gutenberg"))
    p.add_argument("--count", type=int, default=200, help="how many books to have in total")
    p.add_argument("--start-id", type=int, default=1)
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    args = p.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    have = len(list(args.out.glob("*.txt")))
    book_id = args.start_id
    while have < args.count and book_id < args.start_id + args.count * 5:
        current = book_id
        book_id += 1
        target = args.out / f"pg{current}.txt"
        if target.exists():
            continue
        req = urllib.request.Request(
            URL.format(id=current), headers={"User-Agent": "findex-student-lab/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                target.write_bytes(resp.read())
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"skip {current}: {exc}")
        else:
            have += 1
            print(f"[{have}/{args.count}] {target.name}")
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
