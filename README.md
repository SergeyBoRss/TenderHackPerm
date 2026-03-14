# TenderHackPerm

Минимальный стартовый шаблон для хакатона:

- `FastAPI` с раздельными роутерами и конфигом
- базовая структура под модели, схемы и работу с БД
- `asyncpg`-пул с подключением на старте приложения
- `repositories/` и SQL-миграции
- `PostgreSQL` в `docker compose`
- `pgvector` extension в PostgreSQL
- переменные окружения через `.env`
- отдельный native backfill embeddings для macOS/Apple Silicon

## Запуск

1. Создать `.env`:

```bash
cp .env.example .env
```

2. Поднять сервисы:

```bash
docker compose up --build
```

Миграции применяются автоматически при старте `api`, потому что контейнер запускает `python -m app.db.migrate` перед `uvicorn`.
Если нужно прогнать их вручную без `docker compose`, используй:

```bash
python -m app.db.migrate
```

Для векторного поиска проект использует Docker-образ `pgvector/pgvector:pg16`, а расширение `vector` включается миграцией автоматически.

3. Проверить API:

- `http://localhost:8000/api/v1/health`
- `http://localhost:8000/docs`

## Импорт Excel

Папка для импорта по умолчанию: `data/imports/`

Имена файлов по умолчанию:

- `data/imports/cte.xlsx`
- `data/imports/contracts.xlsx`

Их можно переопределить через `.env`:

```bash
IMPORT_DATA_DIR=data/imports
IMPORT_CTE_FILENAME=cte.xlsx
IMPORT_CONTRACTS_FILENAME=contracts.xlsx
```

Эндпоинты:

- `DELETE /api/v1/imports/procurement-data` очистить таблицы закупочного домена
- `POST /api/v1/imports/procurement-data/load` загрузить файлы без полной очистки
- `POST /api/v1/imports/procurement-data/refresh` очистить и заново загрузить оба файла

## Аналитика

- `POST /api/v1/analytics/pricing/cte/{cte_id}` рассчитать оценку цены по 3-веточной схеме

Для backfill embeddings используй отдельный native-процесс на macOS Apple Silicon:

```bash
POSTGRES_HOST=localhost EMBEDDINGS_POSTGRES_HOST=localhost python -m app.backfill_cte_embeddings
```

Это сделано отдельно от Docker API, потому что `mlx-embeddings` рассчитан на MLX/macOS, а контейнер `api` работает на Linux-образе.

## Структура

```text
app/
  api/
    main.py
    routers/
  core/
    config.py
  db/
    deps.py
    migrate.py
    migrations/
    session.py
  repositories/
  security/
  models/
  schemas/
  main.py
```

Новые роутеры добавляются в `app/api/routers/`, затем подключаются в `app/api/main.py`.
