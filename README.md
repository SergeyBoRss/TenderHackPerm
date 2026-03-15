# TenderHackPerm

## Решение победителей

Минимальный стартовый шаблон для хакатона:

- `FastAPI` с раздельными роутерами и конфигом
- базовая структура под модели, схемы и работу с БД
- `asyncpg`-пул с подключением на старте приложения
- `repositories/` и SQL-миграции
- `PostgreSQL` в `docker compose`
- `pgvector` extension в PostgreSQL
- переменные окружения через `.env`
- embeddings на `sentence-transformers` внутри backend

## Запуск

## Быстрый старт

```bash
cp .env.example .env
docker compose up --build
```

После старта:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health: `http://localhost:8000/api/v1/health`

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
- `http://localhost:8000/redoc`

Полная спецификация ручек доступна в Swagger UI и ReDoc.

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

Что лежит в `data/imports/`:

- `cte.xlsx` исходный Excel со справочником CTE
- `contracts.xlsx` исходный Excel с контрактами и товарными позициями
- `cte_embeddings_for_postgres.xlsx` готовый Excel c embeddings для загрузки в таблицу `cte_embeddings`
- `cte_embeddings_for_postgres_full.xlsx` расширенная или полная версия Excel c embeddings, если нужно загрузить именно ее, укажи путь явно в `IMPORT_CTE_EMBEDDINGS_FILE` или в теле запроса `POST /api/v1/embeddings/import-from-excel`

Пример настройки для полной версии:

```bash
IMPORT_CTE_EMBEDDINGS_FILE=data/imports/cte_embeddings_for_postgres_full.xlsx
```

Эндпоинты:

- `DELETE /api/v1/imports/procurement-data` очистить таблицы закупочного домена
- `POST /api/v1/imports/procurement-data/load` загрузить файлы без полной очистки
- `POST /api/v1/imports/procurement-data/refresh` очистить и заново загрузить оба файла

## Роутеры

### `system`

- `GET /api/v1/` статус сервиса

### `health`

- `GET /api/v1/health` healthcheck

### `imports`

- `DELETE /api/v1/imports/procurement-data` очистить закупочные таблицы
- `POST /api/v1/imports/procurement-data/load` загрузить Excel без полной очистки
- `POST /api/v1/imports/procurement-data/refresh` очистить и загрузить Excel заново

### `references`

- `GET /api/v1/references/suppliers` список поставщиков
- `GET /api/v1/references/units` список единиц измерения
- `GET /api/v1/references/categories` список категорий

### `cte`

- `POST /api/v1/cte/search` поиск кандидатов CTE по названию и характеристикам
- `POST /api/v1/cte/manual` ручное добавление CTE

### `embeddings`

- `POST /api/v1/embeddings/backfill` пересчет embeddings через backend
- `POST /api/v1/embeddings/import-from-excel` загрузка готовых embeddings из Excel в `cte_embeddings`

### `analytics`

- `POST /api/v1/analytics/pricing/cte/{cte_id}` оценка цены для одного CTE по 3-веточной схеме
- `POST /api/v1/analytics/nmck` расчет НМЦК по корзине

### `analytics-explain`

- `POST /api/v1/analytics/explain/nmck` детальная расшифровка расчета НМЦК: все рассмотренные контракты, присвоенные веса, исключенные данные и причины исключения

### Поиск CTE

Ручка поиска принимает:

- `name` обязательное название товара
- `characteristics` характеристики либо как JSON-объект, либо строкой вида `Ключ:значение;Ключ:значение`
- `unit_id` идентификатор единицы измерения; если передан, будут искаться только CTE, у которых в истории есть позиции с этой единицей
- `category_ids` список идентификаторов категорий; если передан, будут искаться только CTE из этих категорий
- `max_candidates` максимальное количество возвращаемых CTE

Пример:

```json
POST /api/v1/cte/search
{
  "name": "пакет мусорный 20л",
  "characteristics": "Цвет:черный;Объем:20",
  "unit_id": 1,
  "category_ids": [10, 12],
  "max_candidates": 20
}
```

### Формирование весов

При расчете цены для одного `cte` backend сначала собирает историческую выборку кандидатов:

- exact-ветка по категории / производителю
- vector-ветка по similarity embeddings

После объединения выборки:

1. По `unit_price` считается `IQR`
2. Выбросы отсекаются
3. Для оставшихся наблюдений считаются веса

Используются 4 веса:

- `exact_weight`  
  Вес строгой воронки:
  - совпали категория + производитель + регион -> `1.0`
  - совпали категория + производитель -> региональный вес
  - совпала только категория -> региональный вес `* ANALYTICS_CATEGORY_ONLY_MULTIPLIER`
  - ничего не совпало -> региональный вес `* ANALYTICS_FALLBACK_MULTIPLIER`

- `embedding_weight`  
  Берется из cosine similarity embeddings и ограничивается диапазоном `0..1`

- `time_weight`  
  Учитывает давность контракта через half-life:
  - чем старее контракт, тем меньше вес

- `quantity_weight`  
  Учитывает близость исторического объема закупки к целевому объему:
  ```text
  quantity_distance = abs(log(target_quantity + 1) - log(candidate_quantity + 1))
  quantity_weight = exp(-alpha * quantity_distance)
  quantity_weight = max(min_weight, quantity_weight)
  ```

Итоговый вес наблюдения:

```text
final_weight = exact_weight * embedding_weight * time_weight * quantity_weight
```

После этого по `unit_price` считается взвешенная медиана.  
Она и становится `estimated_unit_price` для конкретного `cte`.

### Детальная расшифровка НМЦК

Ручка `POST /api/v1/analytics/explain/nmck` принимает тот же запрос, что и обычная `POST /api/v1/analytics/nmck`, но возвращает расширенную структуру:

- итоговую НМЦК по корзине
- по каждому выбранному `cte`:
  - `min_candidate_unit_price` и `max_candidate_unit_price`
  - `min_filtered_unit_price` и `max_filtered_unit_price`
  - `q1`, `q3`, `iqr_low`, `iqr_high`
  - `considered_contracts` со всеми рассмотренными контрактными позициями
  - `excluded_contracts` с отфильтрованными наблюдениями и причиной исключения

Для каждого рассмотренного контракта возвращаются:

- `contract_id`, `contract_item_id`, цена и количество
- `source_exact` и `source_vector`
- `embedding_similarity`
- все веса:
  - `exact_weight`
  - `region_weight`
  - `embedding_weight`
  - `time_weight`
  - `quantity_weight`
  - `final_weight`
- текстовое `reason` для каждого веса
- `used_in_median` и `exclusion_reason`

## Таблицы

Основные таблицы и справочники в БД:

- `manufacturers` производители
- `categories` категории
- `cte` каталог товаров CTE
- `counterparties` контрагенты
- `purchase_names` наименования закупок
- `procurement_methods` способы закупки
- `units` единицы измерения
- `contracts` контракты
- `contract_items` товарные позиции контрактов
- `cte_embeddings` embeddings для CTE
- `region_geo_cache` кеш геокоординат регионов

## Скрипты

Пересчет embeddings из терминала:

```bash
POSTGRES_HOST=localhost python scripts/backfill_cte_embeddings.py --batch-size 16 --force-rebuild
```

Загрузка готовых embeddings из Excel:

```bash
POSTGRES_HOST=localhost python scripts/load_cte_embeddings_standalone.py --truncate
```

По умолчанию скрипт читает файл `data/imports/cte_embeddings_for_postgres.xlsx`.

Выгрузка таблицы `cte_embeddings` обратно в Excel:

```bash
POSTGRES_HOST=localhost python scripts/export_cte_embeddings_standalone.py
```

По умолчанию файл сохраняется в `data/imports/cte_embeddings_for_postgres.xlsx`.

Отдельные standalone-скрипты в `scripts/`:

- `scripts/backfill_cte_embeddings.py` пересчет embeddings через текущую модель
- `scripts/load_cte_embeddings_standalone.py` загрузка готового Excel в `cte_embeddings`
- `scripts/export_cte_embeddings_standalone.py` выгрузка `cte_embeddings` в Excel

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
  models/
  schemas/
  main.py
```

Новые роутеры добавляются в `app/api/routers/`, затем подключаются в `app/api/main.py`.
