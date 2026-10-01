# Лабораторна 3 — ранжування та модель об'єктів

## Запуск

```bash
uv run python -m findex.index data/gutenberg --out index.pkl --positions
uv run python -m findex.engine index.pkl 'whale AND (sea OR ocean) NOT ship "white whale"' -k 5 -v
uv run python -m findex.lab3_eval data/gutenberg --limit 50   # усі таблиці нижче
uv run pytest && uv run ruff check .
```

Корпус: **50** документів, 144 111 термінів, 6 784 438 токенів (`Index(terms=144_111, docs=50)`); Python 3.13.12.

## Три sanity-перевірки ранжування

1. **Рідкий термін вищий за частий** ✅ — `aacr` (df=1) проти `alarmed` (df=30), tf=1, документ довжиною 140720:

| Scorer | рідкий | частий |
|---|---|---|
| tfidf | 3,912 | 0,511 |
| bm25 | 3,468 | 0,506 |

2. **20-те повторення майже нічого не додає** ✅ — термін `aaron` (df=5), документ середньої довжини:

| tf | 1 | 2 | 5 | 10 | 20 | 21 | 50 |
|---|---|---|---|---|---|---|---|
| tfidf | 2,303 | 3,899 | 6,008 | 7,604 | 9,201 | 9,313 | 11,310 |
| bm25 | 2,191 | 3,144 | 4,256 | 4,824 | 5,169 | 5,187 | 5,401 |

Приріст 20→21 відносно приросту 1→2: TF-IDF **7,0%**, BM25 **1,9%**; BM25 не перевищує стелі (k1+1)·idf = 5,568.

3. **Короткий документ вищий за довгий** ✅ — `aboard`, tf=1 в обох: «Symphony No. 5 in C minor Opus 67» (3298 токенів) проти «The Complete Works of William Shakespeare» (971761 токенів):

| Scorer | короткий | довгий |
|---|---|---|
| tfidf | 1,204 | 1,204 |
| bm25 | 2,123 | 0,316 |

TF-IDF довжину не враховує (бали рівні); BM25 штрафує довгий документ (b=0,75).

## precision@5: TF-IDF vs BM25

Запити подано як `t1 OR t2 OR …`; «релевантні» — документи, назва яких збігається з регулярним виразом із `eval_queries.json`.

| # | Запит | Релевантних у корпусі | TF-IDF P@5 | BM25 P@5 |
|---|---|---|---|---|
| 1 | white whale captain harpoon | 0 | 0,0 | 0,0 |
| 2 | creature monster Frankenstein laboratory | 0 | 0,0 | 0,0 |
| 3 | vampire Transylvania Harker | 0 | 0,0 | 0,0 |
| 4 | Holmes Watson detective Baker Street | 1 | 0,2 | 0,2 |
| 5 | Alice rabbit hole Wonderland queen | 1 | 0,2 | 0,2 |
| 6 | Elizabeth Darcy Bennet Netherfield | 0 | 0,0 | 0,0 |
| 7 | Pip convict Estella Havisham | 0 | 0,0 | 0,0 |
| 8 | Nautilus Captain Nemo submarine | 0 | 0,0 | 0,0 |
| 9 | Jekyll Hyde Utterson potion | 0 | 0,0 | 0,0 |
| 10 | Odysseus suitors Penelope Ithaca | 0 | 0,0 | 0,0 |
| | **Середнє** (2 запитів) | | **0,20** | **0,20** |

Запити без релевантних документів у корпусі (виключено): white whale captain harpoon; creature monster Frankenstein laboratory; vampire Transylvania Harker; Elizabeth Darcy Bennet Netherfield; Pip convict Estella Havisham; Nautilus Captain Nemo submarine; Jekyll Hyde Utterson potion; Odysseus suitors Penelope Ithaca

## Сліди @timed і кешу

Запит виконано двічі підряд:

```
DEBUG match_ids took 0.333 ms [cache miss]
DEBUG match_ids cache: CacheInfo(hits=0, misses=1, maxsize=256, currsize=1)
DEBUG search took 0.726 ms
DEBUG match_ids took 0.002 ms [cache hit]
DEBUG match_ids cache: CacheInfo(hits=1, misses=1, maxsize=256, currsize=1)
DEBUG search took 0.193 ms
```

Крок «запит → id документів» (`match_ids`): miss 0,333 мс, hit 0,001 мс; `CacheInfo(hits=2, misses=1, maxsize=256, currsize=1)`.

## Демо запиту з дужками й фразою

`whale AND (sea OR ocean) NOT ship "white whale"`

