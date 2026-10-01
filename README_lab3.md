# Лабораторна 3 — ранжування та модель об'єктів

## Запуск

```bash
uv run python -m findex.index data/gutenberg --out index.pkl --positions
uv run python -m findex.engine index.pkl 'whale AND (sea OR ocean) NOT ship "white whale"' -k 5 -v
uv run python -m findex.lab3_eval data/gutenberg --limit 50   # усі таблиці нижче
uv run pytest && uv run ruff check .
```

Корпус: **200** документів, 507 861 термінів, 20 843 816 токенів (`Index(terms=507_861, docs=200)`); Python 3.13.12.

## Три sanity-перевірки ранжування

1. **Рідкий термін вищий за частий** ✅ — `aaanthor` (df=1) проти `accompanied` (df=120), tf=1, документ довжиною 104678:

| Scorer | рідкий | частий |
|---|---|---|
| tfidf | 5,298 | 0,511 |
| bm25 | 4,888 | 0,511 |

2. **20-те повторення майже нічого не додає** ✅ — термін `abolition` (df=20), документ середньої довжини:

| tf | 1 | 2 | 5 | 10 | 20 | 21 | 50 |
|---|---|---|---|---|---|---|---|
| tfidf | 2,303 | 3,899 | 6,008 | 7,604 | 9,201 | 9,313 | 11,310 |
| bm25 | 2,278 | 3,257 | 4,387 | 4,961 | 5,308 | 5,326 | 5,540 |

Приріст 20→21 відносно приросту 1→2: TF-IDF **7,0%**, BM25 **1,8%**; BM25 не перевищує стелі (k1+1)·idf = 5,707.

3. **Короткий документ вищий за довгий** ✅ — `abused`, tf=1 в обох: «Symphony No. 5 in C minor Opus 67» (3298 токенів) проти «The Project Gutenberg Encyclopedia, Volume 1 of 28» (1358851 токенів):

| Scorer | короткий | довгий |
|---|---|---|
| tfidf | 1,204 | 1,204 |
| bm25 | 2,128 | 0,187 |

TF-IDF довжину не враховує (бали рівні); BM25 штрафує довгий документ (b=0,75).

## precision@5: TF-IDF vs BM25

Запити подано як `t1 OR t2 OR …`; «релевантні» — документи, назва яких збігається з регулярним виразом із `eval_queries.json`.

| # | Запит | Релевантних у корпусі | TF-IDF P@5 | BM25 P@5 |
|---|---|---|---|---|
| 1 | Ahab Ishmael Queequeg whale Pequod | 1 | 0,2 | 0,2 |
| 2 | Frankenstein creature Geneva Victor monster | 1 | 0,2 | 0,2 |
| 3 | Alice rabbit Queen Hatter Cheshire | 2 | 0,4 | 0,2 |
| 4 | Jekyll Hyde Utterson Lanyon | 2 | 0,4 | 0,4 |
| 5 | Nemo Nautilus Aronnax submarine | 1 | 0,2 | 0,2 |
| 6 | Holmes Watson Baker Street Lestrade | 2 | 0,4 | 0,4 |
| 7 | Tarzan Jane Africa ape Kala | 6 | 1,0 | 1,0 |
| 8 | Dorothy Toto Scarecrow Tin Woodman Oz | 2 | 0,4 | 0,4 |
| 9 | Huckleberry Tom Sawyer Jim raft Mississippi | 4 | 0,8 | 0,8 |
| 10 | Mars Barsoom Carter Dejah Thoris | 4 | 0,8 | 0,8 |
| | **Середнє** (10 запитів) | | **0,48** | **0,46** |

## Сліди @timed і кешу

Запит виконано двічі підряд:

```
DEBUG match_ids took 1.481 ms [cache miss]
DEBUG match_ids cache: CacheInfo(hits=0, misses=1, maxsize=256, currsize=1)
DEBUG search took 2.375 ms
DEBUG match_ids took 0.003 ms [cache hit]
DEBUG match_ids cache: CacheInfo(hits=1, misses=1, maxsize=256, currsize=1)
DEBUG search took 0.276 ms
```

Крок «запит → id документів» (`match_ids`): miss 1,481 мс, hit 0,001 мс; `CacheInfo(hits=2, misses=1, maxsize=256, currsize=1)`.

## Демо запиту з дужками й фразою

`whale AND (harpoon OR sea) NOT Tarzan "white whale"`

- **13,752** — Moby-Dick; or, The Whale: …were tossed helter-skelter into the **white** curdling cream of the squall. Squall, **whale**, and **harpoon** had all blended together; and the **whale**, merely grazed by the iron…
- **13,526** — Twenty Thousand Leagues under the Sea: …its flat head, which is entirely black. Anatomically, it is distinguished from the **white** **whale** and the North Cape **whale** by the seven cervical vertebrae, and it has two more…
