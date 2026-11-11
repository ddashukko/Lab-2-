# Лабораторна: NoSQL vs SQL — система управління навчальними курсами

Продовження лабораторної про БД для системи управління навчальними курсами на PostgreSQL.
Контент курсів, модулі, матеріали, тести, і спроби проходження тестів винесено в **MongoDB**.
Те саме реалізовано в **PostgreSQL**, і швидкість обох варіантів порівняно.
Друга NoSQL-база — **Redis**.

## Що де лежить

| Папка / файл                | Що там                                                      |
| --------------------------- | ----------------------------------------------------------- |
| `sql/01_base_schema.sql`    | Таблиці з попередньої лаби                                  |
| `sql/02_course_content.sql` | Нові таблиці: курси, матеріали, тести, спроби (SQL-варіант) |
| `sql/03_indexes.sql`        | Індекси                                                     |
| `mongo/setup.js`            | Колекції MongoDB з перевіркою структури документів          |
| `mongo/indexes.js`          | Індекси MongoDB                                             |
| `mongo/queries.js`          | Приклади запитів до MongoDB                                 |
| `lab/datagen.py`            | Генерує тестові дані (однакові для обох БД)                 |
| `lab/load.py`               | Створює таблиці й колекції і заповнює їх даними             |
| `lab/access.py`             | Однакові запити для MongoDB і PostgreSQL                    |
| `lab/verify.py`             | Перевіряє, що обидві БД повертають однакові результати      |
| `lab/bench.py`              | Тести швидкості                                             |
| `lab/charts.py`             | Малює графіки за результатами                               |
| `lab/redis_demo.py`         | Основні команди Redis (пункт 6)                             |
| `results/`                  | Результати: цифри, графіки, протокол команд Redis           |

## Як запустити

Потрібні PostgreSQL, MongoDB, Redis і Python 3.11+.

```bash
pip install "psycopg[binary]" pymongo redis matplotlib

python -m lab.load --scale S     
python -m lab.verify              
python -m lab.bench --scale S     
python -m lab.charts              
python -m lab.redis_demo         
mongosh mongodb://localhost:27017/lms mongo/queries.js
```

Підключення за замовчуванням — до localhost (логін/пароль PostgreSQL: postgres/postgres).
Змінити можна через змінні середовища `PG_DSN`, `MONGO_URI`, `REDIS_URL`.
