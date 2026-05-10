# FPGA Cluster Management Platform

Прототип гибридной информационной системы программно-аппаратной интеграции ПЛИС.  
Реализован по архитектуре «мастер-рабочий узел» (master-worker) с принципами чистой архитектуры.

---

## Структура проекта

```
sources/
├── fpga-master/          # Мастер-узел (FastAPI, etcd, Redis)
│   └── src/
│       ├── entities/     # Доменные сущности (Task, Project, FPGADevice, Token)
│       ├── ports/        # Абстрактные интерфейсы (порты)
│       ├── usecases/     # Бизнес-логика (MasterUseCases, TokenUseCases)
│       ├── adapters/     # Инфраструктура (EtcdAdapter, RedisAdapter)
│       └── controllers/  # FastAPI роутеры (cluster, worker, fpga, task, auth)
├── fpga-worker/          # Рабочий узел (FastAPI, Redis polling)
├── fpga-emulator/        # Эмулятор физической ПЛИС (FastAPI)
├── fpgactl/              # CLI-инструмент управления кластером (аналог kubectl)
├── tests/                # Интеграционные, E2E, нагрузочные, auth, failover тесты
├── docker-compose.yaml   # Полный стек: 3 мастера, 2 воркера, 3 эмулятора, Redis, etcd, Prometheus
├── plot_results.py       # Построение графиков нагрузочных тестов
└── prometheus.yml        # Конфигурация Prometheus
```

---

## Быстрый старт

### Требования
- Docker + Docker Compose v2
- Python ≥ 3.10 (для тестов и fpgactl)

### Запуск кластера

```bash
cd sources/
docker compose up -d
```

Дождаться запуска (~15 сек):

```bash
docker compose ps
```

Все контейнеры должны быть в состоянии `Up`.

### Проверка работоспособности

```bash
# Мастер-узел 1 (без токена — публичный эндпоинт)
curl http://localhost:3030/health

# Кворум кластера
curl -H "X-API-Token: secret-token" http://localhost:3030/quorum
```

---

## Сервисы и порты

| Сервис             | Внешний порт | Описание                               |
|--------------------|-------------|----------------------------------------|
| fpga-master-1      | 3030        | Основной мастер-узел (REST API)        |
| fpga-master-2      | 3031        | Второй мастер-узел (HA)               |
| fpga-master-3      | 3032        | Третий мастер-узел (нечётный кворум)  |
| fpga-worker-1      | 4031        | Рабочий узел (теги: test, dev)        |
| fpga-worker-2      | 4032        | Рабочий узел (теги: prod, staging)    |
| fpga-emulator-1    | 4001        | Эмулятор ПЛИС (xc7a100t, Xilinx)     |
| fpga-emulator-2    | 4002        | Эмулятор ПЛИС (nexus_a7, Lattice)    |
| fpga-emulator-3    | 4003        | Эмулятор ПЛИС (xc7a100t, Xilinx)     |
| Redis              | 6379        | Очереди задач                          |
| etcd               | 2379        | Состояние кластера (Raft)             |
| fpga-dashboard     | 8080        | Web-дашборд кластера (nginx + JS)     |
| Prometheus         | 9090        | Метрики                                |

---

## Балансировка нагрузки между мастерами

Дашборд (`fpga-dashboard`) проксирует все API-запросы через nginx с **круговой балансировкой по наименьшей нагрузке** (`least_conn`) между всеми тремя мастер-узлами.

```
Browser → nginx (port 8080)
                ↓
         upstream fpga_masters  (least_conn)
         ├── fpga-master-1:3030
         ├── fpga-master-2:3030
         └── fpga-master-3:3030
```

Конфигурация в [`fpga-dashboard/nginx.conf.template`](fpga-dashboard/nginx.conf.template):

```nginx
upstream fpga_masters {
    least_conn;
    server fpga-master-1:3030;
    server fpga-master-2:3030;
    server fpga-master-3:3030;
}
```

**Поведение при отказе мастера:**  
Если один из мастеров недоступен, nginx автоматически исключает его из ротации и переключается на оставшиеся. Кворум при этом сохраняется (2 из 3 активны), состояние кластера остаётся `ha`.

**Прямой доступ к мастерам** (без балансировки):  
| Мастер | Порт  |
|--------|-------|
| master-1 | 3030 |
| master-2 | 3031 |
| master-3 | 3032 |

```bash
# Проверить каждый мастер напрямую
for port in 3030 3031 3032; do
  echo -n "master:$port → "; curl -s http://localhost:$port/health | python3 -c "import sys,json; h=json.load(sys.stdin); print(h.get('node_id','?'), h.get('quorum_state','?'))"
done
```

---

## Кворум и отказоустойчивость

Кластер использует алгоритм Raft через etcd. Допустимые конфигурации мастер-узлов:

| Кол-во мастеров | Состояние       | Отказоустойчивость |
|-----------------|-----------------|---------------------|
| 0               | `no_masters`    | 0                   |
| 1               | `standalone`    | 0                   |
| 2               | **`warning`**   | 0 (split-brain риск)|
| 3               | `ha`            | 1 узел              |
| 4               | **`warning`**   | 0 (split-brain риск)|
| 5               | `ha`            | 2 узла              |

**Правило**: чётное количество мастеров всегда переводит кластер в состояние `warning`.

```bash
# Текущий статус кворума
curl -H "X-API-Token: secret-token" http://localhost:3030/quorum
```

---

## Дашборд (Web UI)

Визуализация состояния кластера в реальном времени.  
Стек: vanilla JS + Chart.js, сборка через Node.js/npm, раздача через nginx.

```
http://localhost:8080
```

**Возможности:**
- Состояние кластера, кворум, отказоустойчивость
- Список воркеров с тегами, загрузкой (прогресс-бар), heartbeat
- Список ПЛИС со статусом (idle/busy), моделью, временем последней прошивки
- Графики: история глубины очереди, распределение задач по статусам, загрузка воркеров
- Таблица задач (последние 30) с типом, статусом, тегом и ПЛИС
- Управление токенами (только роль `admin`): список, выпуск, отзыв
- Переключение светлой / тёмной темы кнопкой ☀ / 🌙 (сохраняется в `localStorage`)

**Запуск отдельно:**
```bash
docker compose build fpga-dashboard
docker compose up -d fpga-dashboard
```

**Для локальной разработки (без Docker):**
```bash
cd fpga-dashboard
npm install
npm run dev   # запускает http-сервер на порту 8080
# укажите в браузере http://localhost:8080 и введите токен
```

---

## Аутентификация и RBAC

### Получение root-токена

Root-токен задаётся через переменную окружения `ROOT_TOKEN` в `docker-compose.yaml`:

```yaml
# fpga-master-1 (и другие мастера):
environment:
  ROOT_TOKEN: "secret-token"   # ← изменить в production!
```

При старте каждый мастер автоматически регистрирует root-токен в etcd.  
Root-токен: роль `admin`, бессрочный, **не может быть отозван**.

Чтобы узнать свой токен:
```bash
fpgactl token whoami
# или
curl -H "X-API-Token: secret-token" http://localhost:3030/auth/whoami
```

### Ролевая модель (RBAC)

| Роль       | Ранг | Права                                                           |
|------------|------|-----------------------------------------------------------------|
| `admin`    | 3    | Все операции + управление токенами (выпуск, отзыв, просмотр)   |
| `operator` | 2    | Регистрация воркеров/ПЛИС, отправка задач, чтение всего         |
| `viewer`   | 1    | Только чтение (задачи, воркеры, ПЛИС, кворум, очередь)          |

**Публичные эндпоинты** (без токена): `/health`, `/metrics`, `/docs`, `/openapi.json`, `/redoc`

Каждый запрос проверяется через middleware — заголовок `X-API-Token`.  
Недостаточная роль → HTTP 403.

### Выпуск новых токенов

**Через fpgactl (рекомендуется):**
```bash
# Сначала настроить контекст:
python fpgactl/fpgactl.py config use-context http://localhost:3030 --token secret-token

# Токен оператора (CI/CD, бессрочный)
python fpgactl/fpgactl.py token issue --role operator --description "CI/CD pipeline"

# Токен для дашборда (viewer, TTL 30 дней)
python fpgactl/fpgactl.py token issue --role viewer --description "Dashboard" --ttl 2592000

# Список всех токенов
python fpgactl/fpgactl.py token list

# Отозвать токен
python fpgactl/fpgactl.py token revoke <token_id>
```

**Через curl:**
```bash
# Выпуск токена оператора (TTL 1 час)
curl -X POST http://localhost:3030/auth/tokens \
  -H "X-API-Token: secret-token" \
  -H "Content-Type: application/json" \
  -d '{"role": "operator", "description": "CI/CD pipeline", "ttl_seconds": 3600}'

# Список активных токенов (plaintext значение скрыто)
curl -H "X-API-Token: secret-token" http://localhost:3030/auth/tokens

# Отозвать токен по ID
curl -X DELETE "http://localhost:3030/auth/tokens/<token_id>" \
  -H "X-API-Token: secret-token"

# Кто я?
curl -H "X-API-Token: secret-token" http://localhost:3030/auth/whoami
```

---

## fpgactl — CLI управление кластером

Инструмент в стиле `kubectl` для управления кластером.

### Установка

```bash
cd sources/fpgactl
pip install click httpx rich
```

### Первый запуск — настройка контекста

> **Важно:** перед любыми командами нужно задать контекст (URL + токен).  
> Без этого fpgactl пытается подключиться к `localhost:3030` без токена и получает 401/отказ.

```bash
python fpgactl/fpgactl.py config use-context http://localhost:3030 --token secret-token
python fpgactl/fpgactl.py config show
```

Настройки сохраняются в `~/.fpgactl/config.json`.

### Справочник команд

```bash
# ── Состояние кластера ─────────────────────────────────────────
python fpgactl/fpgactl.py health          # здоровье мастера + воркеры
python fpgactl/fpgactl.py who-master      # текущий лидер кворума
python fpgactl/fpgactl.py quorum          # детальный статус кворума

# ── Получить ресурсы ───────────────────────────────────────────
python fpgactl/fpgactl.py get masters     # список мастер-узлов
python fpgactl/fpgactl.py get workers     # список воркеров
python fpgactl/fpgactl.py get fpgas       # список ПЛИС
python fpgactl/fpgactl.py get queue       # очередь задач
python fpgactl/fpgactl.py get tasks       # история задач
python fpgactl/fpgactl.py get task <id>   # задача по ID

# ── Регистрация ────────────────────────────────────────────────
python fpgactl/fpgactl.py register worker \
  --id worker-3 --tags test,dev --ip 192.168.1.10 --capacity 4

python fpgactl/fpgactl.py register fpga \
  --id fpga-prod-001 --worker worker-3 \
  --model xc7a100t-1csg324c --vendor Xilinx --serial SN-001 --interface usb

# ── Отправка задачи ────────────────────────────────────────────
python fpgactl/fpgactl.py submit task \
  --bitstream s3://fpga-artifacts/network-parser/v1.2.3/bitstream.bit \
  --tag test --mode PROD --priority 1 --pipeline manual-001

# ── Управление токенами (admin) ────────────────────────────────
python fpgactl/fpgactl.py token whoami
python fpgactl/fpgactl.py token list
python fpgactl/fpgactl.py token issue --role operator --description "Deploy bot" --ttl 86400
python fpgactl/fpgactl.py token issue --role viewer   --description "Read-only"
python fpgactl/fpgactl.py token revoke <token_id>
```

### Устранение ошибок fpgactl

| Ошибка | Причина | Решение |
|--------|---------|---------|
| `Connection refused` | Кластер не запущен или не задан контекст | `docker compose up -d`, затем `config use-context` |
| `401 Unauthorized` | Неверный токен или токен не задан | `config use-context ... --token <token>` |
| `403 Forbidden` | Недостаточная роль для операции | Выпустить токен с нужной ролью |

---

## REST API (OpenAPI)

Документация: http://localhost:3030/docs

### Ключевые эндпоинты мастера

| Метод  | Путь                          | Роль      | Описание                       |
|--------|-------------------------------|-----------|--------------------------------|
| GET    | /health                       | публичный | Состояние мастера              |
| GET    | /metrics                      | публичный | Prometheus метрики             |
| GET    | /quorum                       | viewer    | Статус кворума                 |
| GET    | /get_masters                  | viewer    | Список мастер-узлов            |
| GET    | /get_workers                  | viewer    | Список рабочих узлов           |
| GET    | /who_master                   | viewer    | Текущий лидер кворума          |
| POST   | /workers/register             | operator  | Регистрация воркера            |
| POST   | /workers/{id}/heartbeat       | operator  | Heartbeat воркера              |
| POST   | /fpgas/register               | operator  | Регистрация ПЛИС               |
| GET    | /fpgas                        | viewer    | Список ПЛИС                    |
| GET    | /fpgas/{id}                   | viewer    | ПЛИС по ID                     |
| POST   | /tasks                        | operator  | Отправить задачу               |
| GET    | /tasks                        | viewer    | Список задач                   |
| GET    | /tasks/{id}                   | viewer    | Задача по ID                   |
| POST   | /tasks/{id}/complete          | operator  | Отметить задачу выполненной    |
| POST   | /auth/tokens                  | admin     | Выпустить токен                |
| GET    | /auth/tokens                  | admin     | Список токенов                 |
| DELETE | /auth/tokens/{id}             | admin     | Отозвать токен                 |
| GET    | /auth/whoami                  | любой     | Информация о текущем токене    |

---

## Тесты

### Зависимости

```bash
cd sources/
pip install pytest httpx rich click matplotlib numpy
```

### Запуск всех тестов (кроме failover)

```bash
cd sources/
python -m pytest tests/ -v --ignore=tests/test_quorum_failover.py -k "not failover"
```

### Запуск failover-тестов (требуют Docker CLI, ~30 сек)

```bash
python -m pytest tests/test_quorum_failover.py -m failover -v
```

### Категории тестов

| Файл                          | Покрытие                                                         |
|-------------------------------|------------------------------------------------------------------|
| `test_master_api.py`          | REST API мастера: очередь, задачи, ПЛИС, воркеры               |
| `test_worker_api.py`          | REST API воркера: регистрация ПЛИС, выполнение задач            |
| `test_ha.py`                  | HA: 3 мастера, кворум ha, единственный лидер, общий etcd        |
| `test_quorum_failover.py`     | Логика кворума (unit) + failover с Docker stop/start            |
| `test_auth.py`                | Токены, TTL, RBAC, отзыв, защита маршрутов                     |
| `test_cli.py`                 | fpgactl через Click CliRunner                                   |
| `test_e2e.py`                 | Полный пайплайн: 3 тест-проекта + 2 dev/prod, тест-векторы      |
| `test_load.py`                | Нагрузка: c=1/c=10, 100/500/1000/5000/10000 запросов           |

### Нагрузочные тесты и графики

```bash
# Генерация CSV (c=1 и c=10, 100–10000 запросов)
python -m pytest tests/test_load.py::TestLoadMaster::test_generate_summary_csvs -v

# Построение сравнительных графиков c=1 vs c=10
python plot_results.py --results-dir results/ --out-dir results/graphs/
```

Графики сохраняются в `results/graphs/` с русскими подписями и сравнением двух уровней параллелизма:
- `load_get_queue.png` — задержки и RPS для /get_queue (c=1 vs c=10)
- `load_get_workers.png` — для /get_workers
- `load_who_master.png` — для /who_master
- `load_submit_task.png` — для POST /tasks

---

## Пайплайн обработки проектов

```
API → Очередь Redis → Планировщик → Воркер (по worker_tag) → Прошивка ПЛИС → [Тест-последовательность]
```

### Поля задачи (Task)

| Поле            | Описание                                                       |
|-----------------|----------------------------------------------------------------|
| `worker_tag`    | Тег воркера для маршрутизации: `test`, `dev`, `prod`          |
| `fpga_tag`      | Идентификатор ПЛИС: `fpga-test-001`, `dev_<name>`, `prod_<name>` |
| `is_test`       | Флаг: запустить тест-последовательность после прошивки         |
| `tests_url`     | S3-ссылка на тест-векторы (если `is_test=True`)               |
| `test_interface`| Интерфейс ПЛИС для тестирования: `usb`, `jtag`, `ethernet`   |
| `project_name`  | Название проекта                                               |

### Типы проектов

| Тип      | `worker_tag` | `fpga_tag`             | `is_test` | Описание                        |
|----------|--------------|------------------------|-----------|---------------------------------|
| Тестовый | `test`       | `fpga-test-001`        | `true`    | Прошивка + тест-векторы         |
| Dev      | `dev`        | `dev_<project_name>`   | `false`   | Прошивка на отладочный стенд    |
| Prod     | `prod`       | `prod_<project_name>`  | `false`   | Прошивка в production           |

### Пример: тестовый проект

```bash
curl -X POST http://localhost:3030/tasks \
  -H "X-API-Token: secret-token" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "test",
    "mode": "TEST",
    "bitstream_url": "s3://fpga-artifacts/network-parser/v1.2.3/bitstream.bit",
    "worker_tag": "test",
    "fpga_tag": "fpga-test-001",
    "project_name": "Network Parser",
    "is_test": true,
    "tests_url": "s3://fpga-testvectors/network-parser/v1.2.3/vectors.json",
    "test_interface": "usb"
  }'
```

### Визуализация пайплайна

Скрипт подключается к живому кластеру, прогоняет 3 тестовых проекта через полный пайплайн
и строит 4 графика с реальными данными.

```bash
# Полный прогон с реальными данными (требует запущенного кластера)
python visualize_pipeline.py --out-dir results/graphs/

# Только структурные схемы (без кластера)
python visualize_pipeline.py --skip-run --out-dir results/graphs/
```

#### Demo-режим (реалистичные задержки ПЛИС)

По умолчанию кластер работает в быстром режиме (2–5 с на прошивку). Для демонстрации
реальных задержек ПЛИС (35–160 с) измените переменные окружения в `docker-compose.yaml`:

```yaml
# Для каждого fpga-emulator:
PROGRAM_TIME_MIN_S: "35"              # минимальное время прошивки (сек)
PROGRAM_TIME_MAX_S: "160"             # максимальное время прошивки (сек)
TEST_TIME_PER_VECTOR_MIN_S: "60"      # сек на тест-вектор (min)
TEST_TIME_PER_VECTOR_MAX_S: "180"     # сек на тест-вектор (max)
```

Или использовать готовый override-файл:
```bash
docker compose -f docker-compose.yaml -f docker-compose.demo.yaml up -d --build
```

Затем запустите визуализацию — скрипт выведет прогресс каждого проекта с таймингами.

Изображения в `results/graphs/`:
- `pipeline_architecture.png` — блок-схема пайплайна
- `pipeline_routing.png` — маршрутизация по воркерам и ПЛИС
- `pipeline_test_results.png` — реальные результаты тест-последовательностей
- `pipeline_timeline.png` — реальная хронология выполнения задач

---

## Архитектура (Clean Architecture)

```
entities/    ← доменные объекты (Task, FPGADevice, ClusterToken, Project)
ports/       ← абстрактные интерфейсы (ABC)
usecases/    ← бизнес-логика (MasterUseCases, TokenUseCases)
adapters/    ← конкретные реализации (EtcdHTTPClient, Redis)
controllers/ ← FastAPI роутеры + RBAC зависимости
main.py      ← composition root: сборка зависимостей, auth middleware
```

**Паттерн Factory** в воркере:
`FPGAConnectionFactory.create("usb" | "ethernet" | "jtag" | "pcie", emulator_url)`

**RBAC middleware** (глобальный) — проверяет `X-API-Token` на всех маршрутах,  
кроме `/health`, `/metrics`, `/docs`. Роли: `admin > operator > viewer`.

---

## Метрики (Prometheus)

На `/metrics` каждого сервиса:

**Master:** `master_tasks_submitted_total`, `master_tasks_completed_total{status}`,
`master_workers_online`, `master_fpgas_total`, `master_queue_depth`

**Worker:** `worker_tasks_executed_total{status}`, `worker_fpgas_registered`, `worker_fpgas_busy`

**Emulator:** `emulator_program_total{result}`, `emulator_test_total{result}`,
`emulator_program_duration_seconds`, `emulator_test_duration_seconds`

Эндпоинт `/run_test_sequence` принимает список тест-векторов `[{input, expected_output, label}]`
и возвращает постасочный отчёт `{total, passed, failed, pass_rate, cases[]}`.


---

## Остановка кластера

```bash
docker compose down
# или с удалением данных
docker compose down -v
```
