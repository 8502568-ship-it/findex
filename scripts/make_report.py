"""Збирає звіт Лаби 2 (docx у форматі Лаби 1) і README-розділ із results.json.

    uv add --dev python-docx
    uv run python make_report.py --template лаб1.docx --results results.json \
        --out "Лабораторна2_звіт.docx" --readme README_lab2.md
Усі числа й порівняльні висновки беруться з results.json (твої вимірювання).
"""
from __future__ import annotations

import argparse
import json
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.shared import Pt

REPO = "https://github.com/8502568-ship-it/findex"


DRAFT = False  # --draft: замість чисел — підсвічені «[X]» (для ручного заповнення)


def n1(x, d=1):
    return "[X]" if DRAFT else f"{x:.{d}f}".replace(".", ",")


def big(x):
    return "[X]" if DRAFT else f"{x:,}".replace(",", " ")


def draft_results():
    """Фіктивні (ненульові) дані: форму звіту видно, числа підміняються на [X]."""
    mem = [{"name": nm, "variant": v, "current_mib": c, "peak_mib": c + 1, "build_s": 1,
            "file_mib": 1.0, "load_ms": 1.0}
           for nm, v, c in [("list[Posting], звичайний @dataclass", "plain", 3.0),
                            ("list[Posting], slots=True", "slots", 2.0),
                            ("array('I') пари", "array", 1.0)]]
    return {"python": "3.13", "limit": 50, "n_docs": "[X]", "n_terms": 1, "n_postings": 1000,
            "sizes": {k: "[X]" for k in ("plain_obj", "plain_dict", "slots_obj", "int", "array_item")},
            "memory": mem,
            "formats": [{"name": n, "file_mib": 1.0, "save_ms": 1.0, "load_ms": 1.0}
                        for n in ("pickle", "json", "binary")],
            "merge_set": [{"label": lb, "x": "[X]", "dx": "[X]", "y": "[X]", "dy": "[X]",
                           "merge_us": 1.0, "set_us": 2.0}
                          for lb in ("2 найчастіших", "2 найрідкісніших", "найчастіший + найрідкісніший")],
            "positions": [{"flag": False, "current_mib": 1.0, "peak_mib": 1.0, "file_mib": 1.0},
                          {"flag": True, "current_mib": 2.0, "peak_mib": 2.0, "file_mib": 2.0}]}


# =============================== ТЕКСТ ЗВІТУ ================================
def results_blocks(R):
    """Розділи 5-6: таблиці та аналіз. Повертає список блоків."""
    mem = {r["variant"]: r for r in R["memory"]}
    P, S, A = mem["plain"], mem["slots"], mem["array"]
    n = R["n_postings"]
    bpp = lambda r: r["current_mib"] * 2**20 / n
    sz = R["sizes"]
    F = {r["name"]: r for r in R["formats"]}
    B: list = []
    lim = R["limit"]
    B.append(("p", f"Машина: AMD Ryzen 3 7320U, 16 ГБ RAM, Windows, Python {R['python']}. "
              f"Вимірювання виконано на {R['n_docs']} документах корпусу "
              f"({big(R['n_terms'])} унікальних термінів, {big(n)} постінгів)"
              + (f" — перші {lim} документів (прапорець --limit: під tracemalloc збірка індексу повільна, як і в Лабі 1)." if lim else ".")))
    B.append(("cap", "Таблиця 3 — три способи зберігання постінгів (M4)"))
    B.append(("table", ["Представлення постінгів", "В пам’яті після збірки, МіБ", "Пік (build), МіБ",
                        "Файл (pickle), МіБ", "Load, мс"],
              [[r["name"], n1(r["current_mib"]), n1(r["peak_mib"]), n1(r["file_mib"], 2),
                n1(r["load_ms"], 0)] for r in R["memory"]]))
    B.append(("cap", "Таблиця 4 — формати збереження (M3)"))
    B.append(("table", ["Формат", "Файл, МіБ", "Save, мс", "Load, мс"],
              [[{"pickle": "pickle (slots-dataclass)", "json": "json (пари [doc_id, tf])",
                 "binary": "binary: JSON-заголовок + array('I') + mmap"}[r["name"]],
                n1(r["file_mib"], 2), n1(r["save_ms"], 0), n1(r["load_ms"])] for r in R["formats"]]))
    B.append(("cap", "Таблиця 5 — merge проти set (операція AND над двома списками)"))
    B.append(("table", ["Пара", "Терміни (df)", "merge, мкс", "set, мкс", "Швидший"],
              [[r["label"], f"{r['x']} ({r['dx']}), {r['y']} ({r['dy']})", n1(r["merge_us"]),
                n1(r["set_us"]), "[X]" if DRAFT else ("merge" if r["merge_us"] < r["set_us"] else "set")]
               for r in R["merge_set"]]))
    p0, p1 = R["positions"]
    B.append(("cap", "Таблиця 6 — ціна прапорця --positions (slots)"))
    B.append(("table", ["positions", "В пам’яті, МіБ", "Пік, МіБ", "Файл (pickle), МіБ"],
              [[str(r["flag"]), n1(r["current_mib"]), n1(r["peak_mib"]), n1(r["file_mib"], 2)]
               for r in (p0, p1)]))

    # ---- аналіз ----
    B.append(("h1", "6. Аналіз результатів"))
    a_ps, a_sa, a_pa = P["current_mib"] / S["current_mib"], S["current_mib"] / A["current_mib"], P["current_mib"] / A["current_mib"]
    B.append(("p", f"**Куди пішли байти (M4).** Після побудови індекс займає {n1(P['current_mib'])} МіБ "
              f"у варіанті зі звичайним dataclass, {n1(S['current_mib'])} МіБ зі slots=True та "
              f"{n1(A['current_mib'])} МіБ у варіанті array('I'), тобто ≈{n1(bpp(P),0)}, ≈{n1(bpp(S),0)} і "
              f"≈{n1(bpp(A),0)} байтів на постінг. slots економить ×{n1(a_ps)} проти звичайного dataclass, "
              f"array — ще ×{n1(a_sa)} проти slots і ×{n1(a_pa)} загалом."))
    d_ps = (P["current_mib"] - S["current_mib"]) * 2**20 / n
    B.append(("p", f"Розкладання за варіантами. Звичайний dataclass: об’єкт ({sz['plain_obj']} Б за sys.getsizeof) "
              f"плюс сховище атрибутів екземпляра, плюс два int по {sz['int']} Б (значення понад 256 не кешуються), "
              f"плюс 8-байтовий вказівник у списку. slots=True прибирає сховище атрибутів у вигляді __dict__: "
              f"виміряна економія — ≈{n1(d_ps,0)} Б на постінг (об’єкт slots — {sz['slots_obj']} Б); точне число залежить від версії "
              f"CPython (у 3.13 значення атрибутів можуть зберігатися вбудовано), тому спиратися слід на виміряну різницю, а не на розмір __dict__. "
              f"array('I'): рівно 4 Б на doc_id і 4 Б на tf — 8 Б на постінг без об’єктів, заголовків і вказівників; "
              f"решта виміряного ({n1(bpp(A),0)} Б) — словник термінів, doc_meta і doc_lengths, які не залежать від способу зберігання постінгів. "
              f"Ціна array: немає positions, а постінги — це два паралельні масиви, а не об’єкти з іменованими полями."))
    B.append(("p", f"**Пік проти залишку.** Пік збірки перевищує залишок на {n1(P['peak_mib']-P['current_mib'])}, "
              f"{n1(S['peak_mib']-S['current_mib'])} і {n1(A['peak_mib']-A['current_mib'])} МіБ відповідно. Це "
              f"тимчасові об’єкти поточного документа (текст книги, копії після normalize/casefold, Counter), "
              f"як і в Лабі 1: вони майже однакові для всіх варіантів, тому саме стовпець «в пам’яті після збірки» "
              f"показує ціну структури даних, а пік — ціну процесу збірки."))
    pk, js, bn = F["pickle"], F["json"], F["binary"]
    B.append(("p", f"**Формати (M3).** Файл: pickle {n1(pk['file_mib'],2)} МіБ, json {n1(js['file_mib'],2)} МіБ, "
              f"binary {n1(bn['file_mib'],2)} МіБ. Завантаження: pickle {n1(pk['load_ms'],0)} мс, "
              f"json {n1(js['load_ms'],0)} мс, binary {n1(bn['load_ms'])} мс "
              f"(×{n1(pk['load_ms']/max(bn['load_ms'],1e-9),0)} швидше за pickle). pickle та json мусять відновити "
              f"кожен об’єкт Posting, тож час load росте разом із кількістю постінгів; binary читає лише "
              f"JSON-заголовок (терміни та зміщення), а самі постінги відображаються через mmap і читаються "
              f"лише для термінів із запиту. pickle лишається зручним для власних файлів, але небезпечним для чужих (див. нижче); "
              f"у pickle slots-dataclass відновлюється повільніше за звичайний, що видно у стовпці Load таблиці 3."))
    ms = R["merge_set"]
    wins = [r for r in ms if r["merge_us"] < r["set_us"]]
    rows = "; ".join(f"{r['label']}: merge {n1(r['merge_us'])} мкс проти set {n1(r['set_us'])} мкс" for r in ms)
    if DRAFT:
        why = ("[X: хто швидший у кожному випадку й чому — set виконується в C, merge — цикл на Python, "
               "але merge не будує хеш-таблиць і краще, коли один список дуже короткий]")
    elif not wins:
        why = ("set виграв у всіх трьох випадках. Обидва підходи лінійні, O(|a|+|b|), але побудова множин і перетин "
               "виконуються в C, а двовказівниковий merge — цикл на Python, тому на списках у RAM set швидший.")
    elif len(wins) == len(ms):
        why = ("merge виграв у всіх випадках: списки вже відсортовані, тож merge не витрачає часу на побудову "
               "хеш-таблиць, яку змушений робити set.")
    else:
        names = ", ".join(r["label"] for r in wins)
        why = (f"merge виграв у випадках: {names}; у решті швидшим був set. Там, де один зі списків дуже короткий, "
               "merge уникає побудови множини з довгого списку; на двох довгих списках виграє set, бо виконується в C.")
    B.append(("p", f"**merge проти set.** {rows}. {why} Практично: merge не створює додаткових структур і працює "
              f"потоково та зі стиснутими постінгами, тому саме його використовують справжні рушії й саме він "
              f"розширюється на фразові запити."))
    B.append(("p", f"**Позиції.** Прапорець --positions збільшує індекс у пам’яті з {n1(p0['current_mib'])} до "
              f"{n1(p1['current_mib'])} МіБ (×{n1(p1['current_mib']/p0['current_mib'])}), файл pickle — з "
              f"{n1(p0['file_mib'],2)} до {n1(p1['file_mib'],2)} МіБ (×{n1(p1['file_mib']/p0['file_mib'])}). "
              f"За цю ціну індекс отримує можливість фразового пошуку (Лаба 3)."))
    B.append(("h2", "Безпека pickle"))
    B.append(("p", "pickle.load виконує довільний код: у файлі може бути об’єкт, чий __reduce__ викликає, наприклад, "
              "os.system(...), і код спрацює під час load. Тому pickle допустимий лише для власноруч створених файлів; "
              "для обміну даними використовуються json або бінарний формат, який лише читає байти. "
              "У store.py це задокументовано коментарем біля load_pickle."))
    return B


def reflection_blocks(R):
    mem = {r["variant"]: r for r in R["memory"]}
    S, A = mem["slots"], mem["array"]
    n = R["n_postings"]
    N = S["current_mib"] / A["current_mib"]
    sz = R["sizes"]
    Q = [
        ("Намалюйте хеш-таблицю на 8 слотів із колізією та покажіть пошук.",
         "Слот = hash(key) & 7. Ключі A і B дають слот 3: A лежить у слоті 3. При вставці B слот зайнятий, тож CPython "
         "береться за послідовність probe, що підмішує старші біти хешу (perturb), і кладе B в інший слот, наприклад 5. "
         "Пошук B: слот 3 → там A, хеш і значення не збігаються → наступний слот за тією ж послідовністю (5) → збіг → знайдено."),
        ("Контракт хешування; як словник «губить» ключ.",
         "Якщо a == b, то hash(a) == hash(b). Клас із __eq__ за полем x, але з __hash__ = id(self): A(1) == A(1), "
         "проте хеші різні, тож d[A(1)] = 'v' і наступний d[A(1)] шукає в іншому слоті й дає KeyError — ключ «загубився»."),
        ("Чому list нехешований, а tuple хешований? Чому (1, [2]) нехешований?",
         "Після append у list змінився б хеш, і ключ лежав би не в тому слоті. tuple незмінний, тож хеш стабільний. "
         "Хеш tuple обчислюється рекурсивно від елементів, а hash([2]) дає TypeError."),
        ("Що frozen=True змінює в __hash__? Що буде, якщо визначити __eq__ вручну й забути __hash__?",
         "frozen=True разом з eq=True генерує __hash__ із полів. Якщо вручну визначити __eq__ без __hash__, "
         "Python встановлює __hash__ = None, і об’єкт стає нехешованим."),
        ("Куди діваються ~100 байтів на екземпляр і як їх прибирає __slots__? Чим доводиться платити?",
         f"Це сховище атрибутів екземпляра (__dict__). __slots__ замінює його фіксованими слотами в самому об’єкті; у моїх "
         f"вимірах це дало {n1((mem['plain']['current_mib']-S['current_mib'])*2**20/n,0)} Б економії на постінг. Плата: не можна додавати "
         f"довільні атрибути, немає __weakref__ за замовчуванням, складніше множинне успадкування."),
        ("Рядок array('I') у N разів менший. Звідки N і який розмір елемента в кожному представленні?",
         f"N = {n1(N)} (після збірки: {n1(S['current_mib'])} МіБ проти {n1(A['current_mib'])} МіБ). У array на постінг 8 Б "
         f"(2×u32). У list[Posting]: 8 Б вказівник у списку + {sz['slots_obj']} Б об’єкт + по {sz['int']} Б на кожен int (значення понад 256 "
         f"не кешуються) — виміряно ≈{n1(S['current_mib']*2**20/n,0)} Б на постінг."),
        ("Merge проти set(a) & set(b): складність і результат бенчмарку.",
         "Обидва O(|a|+|b|). merge — потоковий, без додаткової пам’яті, але цикл на Python; set будує дві хеш-таблиці, але в C. "
         "Результат — у таблиці 5 та аналізі."),
        ("Чому pickle.load на завантаженому файлі — це віддалене виконання коду?",
         "Десеріалізація викликає callable, який указав автор файлу (через __reduce__), тобто виконує його код із правами користувача."),
    ]
    return Q


def report_blocks(R):
    B = []
    H1, H2, Pp, C = (lambda t: B.append(("h1", t))), (lambda t: B.append(("h2", t))), \
        (lambda t: B.append(("p", t))), (lambda t: B.append(("code", t)))
    H1("1. Мета роботи")
    Pp("Зрозуміти, як влаштовані словники та множини Python (хеш-таблиця, контракт __hash__/__eq__), "
       "навчитися використовувати collections, dataclasses та __slots__, оцінювати вартість об’єктів у пам’яті; "
       "побудувати другий крок пошукової системи findex — інвертований індекс над лінивим пайплайном Лаби 1, "
       "Boolean-пошук двовказівниковим merge, збереження індексу у двох форматах і вимірювання всіх тверджень числами.")
    Pp("Що вивчається: dict і set (відкрита адресація, resize, компактний впорядкований dict), контракт хешування, "
       "defaultdict і Counter, @dataclass(frozen=True, slots=True), __slots__, array, pickle/json/mmap, tracemalloc.")
    H1("2. Теоретичні відомості")
    H2("2.1. Хеш-таблиця та dict у CPython")
    Pp("Хеш-таблиця перетворює «знайти ключ» на арифметику: hash(key), обмежений розміром таблиці, дає слот. Середній пошук — O(1). "
       "Колізії (два ключі в одному слоті) CPython розв’язує відкритою адресацією: пробує інший слот за послідовністю, що підмішує "
       "старші біти хешу (perturb). Коли таблиця заповнена приблизно на 2/3, вона перебудовується більшою — тому вставка амортизовано O(1).")
    Pp("Починаючи з Python 3.6 dict компактний і впорядкований: маленький розріджений масив індексів вказує на щільний масив "
       "трійок (hash, key, value). Звідси порядок вставки (гарантований з 3.7) і менший розмір. set — та сама таблиця без значень; "
       "frozenset — хешована версія set.")
    H2("2.2. Контракт хешування")
    Pp("Ключ словника має мати __hash__ і __eq__, причому з a == b випливає hash(a) == hash(b). Порушення мовчки «губить» ключі. "
       "Тому змінювані об’єкти (list, dict, set) нехешовані, а tuple хешований лише якщо хешований кожен його елемент. "
       "Клас із __eq__, але без __hash__, отримує __hash__ = None. @dataclass(frozen=True) генерує обидва методи з полів. "
       "Хеш рядків рандомізований для кожного процесу, тому сирі хеші не можна зберігати на диск.")
    H2("2.3. collections")
    Pp("Counter — підклас dict для підрахунку; defaultdict(list) створює значення за замовчуванням через __missing__ "
       "(index[term].append(doc_id) без перевірки наявності ключа); deque дає O(1) на обох кінцях.")
    H2("2.4. dataclasses, __slots__ та компактне зберігання")
    Pp("@dataclass генерує __init__, __repr__, __eq__ за оголошеними полями. frozen=True робить екземпляри незмінними й хешованими; "
       "slots=True (Python 3.10+) замінює словник атрибутів кожного екземпляра фіксованими слотами.")
    C("@dataclass(frozen=True, slots=True)\nclass Posting:\n    doc_id: int\n    tf: int\n    positions: tuple[int, ...] = ()")
    Pp("Для мільйонів малих цілих навіть слотів забагато: int займає 28 Б, а список лише зберігає вказівники. "
       "array('I') зберігає числа як «сирі» 4-байтові значення, тож 1 000 000 чисел займають близько 4 МБ проти десятків МБ для списку int.")
    H2("2.5. Відсортовані постінги та merge")
    Pp("Якщо постінги кожного терміна відсортовані за doc_id, AND обчислюється двома вказівниками: порівнюємо, випускаємо збіг, "
       "просуваємо менший; OR — той самий прохід зі скиданням усіх елементів по одному разу; NOT — різниця. Складність O(|a|+|b|), "
       "без хешування. Альтернатива — set(a) & set(b): простіше, але будує хеш-таблиці.")
    H2("2.6. Збереження на диск")
    Pp("pickle серіалізує майже будь-який граф об’єктів, але pickle.load на чужих даних виконує довільний код. json безпечний, "
       "але повільніший і роздутіший; ключі-числа стають рядками. Спеціалізований бінарний формат (JSON-заголовок term → (зміщення, кількість) "
       "та суцільні буфери array('I')) дозволяє через mmap читати лише потрібні постінги, а час завантаження майже не залежить від розміру індексу.")
    H1("3. Обраний корпус")
    Pp("Використано той самий корпус, що й у Лабі 1: Project Gutenberg, 200 книг (119,1 МіБ, 124 905 823 байти), data/gutenberg/ "
       "(у .gitignore). Інвертований індекс будується поверх пайплайну Лаби 1 (iter_documents → tokenize) без змін у ньому.")
    H1("4. Хід роботи")
    H2("4.1. Структура")
    C("src/findex/\n  corpus.py, tokenize.py, stats.py, eager.py, bench.py (Лаба 1)\n  models.py    # Posting, DocMeta, ObjectIndex, ArrayIndex, MmapIndex\n"
      "  pipeline.py  # адаптер до iter_documents/tokenize Лаби 1\n  index.py     # M1: build_index + CLI\n  search.py    # M2: merge/set, парсер запитів, CLI\n"
      "  store.py     # M3: pickle, json, binary (mmap)\n  bench_lab2.py # M4 і всі таблиці\ntests/test_lab2.py")
    H2("4.2. M1 — побудова індексу (index.py)")
    Pp("Індекс будується одним проходом по лінивому корпусу: для поточного документа рахується Counter, наприкінці документа "
       "його вміст «скидається» в глобальний defaultdict(list). doc_id зростають, тому списки постінгів відсортовані без окремого sort. "
       "Окрім постінгів зберігаються doc_lengths (для BM25 у Лабі 3) та doc_meta (DocMeta з шляхом і назвою книги з заголовка Gutenberg). "
       "Позиції токенів вмикаються прапорцем --positions.")
    C("for doc_id, doc in enumerate(docs):\n    counts = Counter()\n    for tok in tokenize(doc.text):\n        counts[tok] += 1\n"
      "    idx.doc_lengths[doc_id] = sum(counts.values())\n    for term, tf in counts.items():\n        postings[term].append(Posting(doc_id, tf))")
    H2("4.3. M2 — Boolean-пошук (search.py)")
    Pp("Запит «a b» означає AND; підтримуються AND, OR, NOT (верхній регістр), обчислення зліва направо; NOT x означає «AND NOT x». "
       "Двовказівниковий merge реалізовано для AND, OR і NOT (різниця); set-версія — через &, |, −. "
       "Вибір рушія — прапорець --engine {merge,set}. Терміни запиту проходять той самий tokenize, що й документи.")
    C("def merge_and(a, b):\n    i = j = 0; out = []\n    while i < len(a) and j < len(b):\n        if a[i] == b[j]:\n            out.append(a[i]); i += 1; j += 1\n"
      "        elif a[i] < b[j]:\n            i += 1\n        else:\n            j += 1\n    return out")
    H2("4.4. M3 — збереження (store.py)")
    Pp("Реалізовано три формати: pickle (із коментарем про небезпеку load чужого файлу), json та бінарний. Бінарний файл має вигляд "
       "[магічні байти][довжина заголовка][JSON-заголовок: term → (зміщення, кількість), doc_lengths, doc_meta][суцільні буфери array('I')]; "
       "завантажується через mmap, а постінги термінів читаються як memoryview без копіювання. Формат під час load визначається за першими байтами.")
    H2("4.5. M4 — дослідження пам’яті (bench_lab2.py)")
    Pp("Той самий корпус будується трьома способами (звичайний dataclass, slots=True, пари array('I')) під tracemalloc. "
       "Для кожного фіксуються: пам’ять після збірки (поточне значення tracemalloc — це й є ціна структури), пік збірки, "
       "розмір файлу pickle і час load. Додатково вимірюються формати, merge проти set на двох найчастіших і двох найрідкісніших термінах, "
       "та ціна --positions. Запуск: uv run python -m findex.bench_lab2 data/gutenberg --limit 50.")
    H1("5. Результати вимірювань")
    B += results_blocks(R)
    H1("7. Відповіді на контрольні питання")
    for i, (q, a) in enumerate(reflection_blocks(R), 1):
        B.append(("qa", f"{i}.", q, a))
    H1("8. Висновки")
    mem = {r["variant"]: r for r in R["memory"]}
    P, S, A = mem["plain"], mem["slots"], mem["array"]
    F = {r["name"]: r for r in R["formats"]}
    ms = R["merge_set"]
    nwin = sum(r["merge_us"] < r["set_us"] for r in ms)
    Pp("У роботі розібрано внутрішній устрій dict і set, контракт хешування та роль frozen/slots у dataclass; на цій основі "
       "побудовано інвертований індекс findex, що за один прохід по лінивому пайплайну Лаби 1 створює відсортовані постінги, "
       "довжини документів і метадані. Реалізовано Boolean-пошук двовказівниковим merge з set-альтернативою та збереження в трьох форматах.")
    Pp(f"Вимірювання на {R['n_docs']} документах показали: slots=True зменшує індекс у ×{n1(P['current_mib']/S['current_mib'])} проти звичайного dataclass "
       f"({n1(P['current_mib'])} → {n1(S['current_mib'])} МіБ), а зберігання пар array('I') — ще у ×{n1(S['current_mib']/A['current_mib'])} "
       f"({n1(A['current_mib'])} МіБ). Бінарний формат із mmap завантажується за {n1(F['binary']['load_ms'])} мс проти {n1(F['pickle']['load_ms'],0)} мс у pickle. "
       f"Merge виявився швидшим за set у {"[X]" if DRAFT else nwin} із {len(ms)} випадків бенчмарку. Увімкнення позицій збільшує індекс у ×{n1(R['positions'][1]['current_mib']/R['positions'][0]['current_mib'])}.")
    H1("Додаток. Репозиторій")
    B.append(("table", ["Пункт", "Значення"],
              [["Репозиторій", REPO], ["Тег", "lab-02"], ["Тести", "uv run pytest"], ["Лінтер", "uv run ruff check ."],
               ["Побудова індексу", "uv run python -m findex.index data/gutenberg --out index.bin"],
               ["Пошук", 'uv run python -m findex.search index.bin "query" --engine merge'],
               ["Вимірювання", "uv run python -m findex.bench_lab2 data/gutenberg --limit 50"]]))
    return B


# ================================ РЕНДЕРИ ===================================
def _runs(par, text, size, font="Times New Roman"):
    for k, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        for m, sub in enumerate(re.split(r"(\[X[^\]]*\])", part)):
            if not sub:
                continue
            r = par.add_run(sub)
            r.bold = True if k % 2 else None
            r.font.name = font
            r._element.rPr.rFonts.set(qn("w:eastAsia"), font)
            r.font.size = Pt(size)
            if m % 2:
                r.font.highlight_color = WD_COLOR_INDEX.YELLOW


def to_docx(blocks, template, out):
    d = Document(template)
    body = d.element.body
    ps = d.paragraphs
    # титулка: №2 + тема
    def set_text(p, t):
        for r in p.runs[1:]:
            r._element.getparent().remove(r._element)
        p.runs[0].text = t
    for p in ps[:32]:
        if p.text.startswith("Лабораторна робота №"):
            set_text(p, "Лабораторна робота №2")
        elif p.text.startswith("Ітератори, генератори"):
            set_text(p, "Інвертований індекс: словники, хешування та пам’ять")
    # прибрати все після титулки (залишити sectPr)
    cut = next(i for i, p in enumerate(ps) if p.style.name == "Heading 1")
    for el in [p._p for p in ps[cut:]] + [t._tbl for t in d.tables]:
        body.remove(el)
    # розрив сторінки після титулки
    last = d.paragraphs[-1]
    last.add_run().add_break(WD_BREAK.PAGE)

    def border(tbl):
        tblPr = tbl._tbl.tblPr
        from docx.oxml import OxmlElement
        b = OxmlElement("w:tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            e = OxmlElement(f"w:{side}")
            e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:color"), "000000")
            b.append(e)
        tblPr.append(b)

    for blk in blocks:
        k = blk[0]
        if k in ("h1", "h2"):
            p = d.add_paragraph(style="Heading 1" if k == "h1" else "Heading 2")
            _runs(p, blk[1], 23 if k == "h1" else 17)
        elif k == "p":
            p = d.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            _runs(p, blk[1], 14)
        elif k == "bullet":
            p = d.add_paragraph(); _runs(p, "•        " + blk[1], 14)
        elif k == "code":
            for line in blk[1].split("\n"):
                p = d.add_paragraph(); p.paragraph_format.space_after = Pt(0)
                _runs(p, line or " ", 8.5, "Courier New")
        elif k == "cap":
            p = d.add_paragraph(); r = p.add_run(blk[1]); r.italic = True
            r.font.name = "Times New Roman"; r.font.size = Pt(14)
        elif k == "qa":
            p = d.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            _runs(p, f"{blk[1]}     **{blk[2]}** {blk[3]}", 14)
        elif k == "table":
            head, rows = blk[1], blk[2]
            t = d.add_table(rows=1 + len(rows), cols=len(head)); border(t)
            for ci, h in enumerate(head):
                c = t.rows[0].cells[ci]; c.text = ""
                _runs(c.paragraphs[0], f"**{h}**", 11)
            for ri, row in enumerate(rows, 1):
                for ci, v in enumerate(row):
                    c = t.rows[ri].cells[ci]; c.text = ""
                    _runs(c.paragraphs[0], str(v), 11)
            d.add_paragraph()
    d.save(out)


def to_md(blocks):
    L = []
    for blk in blocks:
        k = blk[0]
        if k == "h1": L.append(f"\n## {blk[1]}\n")
        elif k == "h2": L.append(f"\n### {blk[1]}\n")
        elif k in ("p",): L.append(blk[1] + "\n")
        elif k == "bullet": L.append(f"- {blk[1]}")
        elif k == "code": L.append("```\n" + blk[1] + "\n```\n")
        elif k == "cap": L.append(f"**{blk[1]}**\n")
        elif k == "qa": L.append(f"{blk[1]} **{blk[2]}** {blk[3]}\n")
        elif k == "table":
            L.append("| " + " | ".join(blk[1]) + " |")
            L.append("|" + "---|" * len(blk[1]))
            L += ["| " + " | ".join(str(c) for c in r) + " |" for r in blk[2]]
            L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True, help="лаб1.docx")
    ap.add_argument("--results", default="results.json")
    ap.add_argument("--draft", action="store_true", help="чернетка: числа = підсвічені [X]")
    ap.add_argument("--out", default="Лабораторна2_звіт.docx")
    ap.add_argument("--readme", default="README_lab2.md")
    a = ap.parse_args()
    global DRAFT
    DRAFT = a.draft
    if DRAFT:
        R = draft_results()
    else:
        with open(a.results, encoding="utf-8") as f:
            R = json.load(f)
    to_docx(report_blocks(R), a.template, a.out)
    readme = ("## Lab 02 — Інвертований індекс\n\n### Запуск\n\n```bash\n"
              "uv run python -m findex.index data/gutenberg --out index.bin\n"
              "uv run python -m findex.index data/gutenberg --out index.fidx --format binary\n"
              'uv run python -m findex.search index.bin "query" --engine merge\n'
              "uv run python -m findex.bench_lab2 data/gutenberg --limit 50\nuv run pytest\n```\n\n"
              "Запит: `a b` = AND; також `AND`/`OR`/`NOT` (верхній регістр), зліва направо.\n\n### Результати\n\n"
              + to_md(results_blocks(R)) + "\n### Reflection\n\n"
              + "\n".join(f"{i}. **{q}** {ans}" for i, (q, ans) in enumerate(reflection_blocks(R), 1)) + "\n")
    with open(a.readme, "w", encoding="utf-8") as f:
        f.write(readme)
    print("OK:", a.out, a.readme)


if __name__ == "__main__":
    main()
