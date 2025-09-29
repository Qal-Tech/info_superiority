# Design Document: Information Superiority System

## 1. Overview
Краткое описание цели проекта и общей идеи:
- Поддержка аналитиков и исследователей
- Работа с большими объемами событийных данных
- Интеграция ML-модулей (например, дедупликация, граф-анализ)

---

## 2. System Goals
- Сбор и нормализация событий из разных источников
- Обеспечение полноты и прослеживаемости данных (provenance)
- Интерактивная аналитика (графы, временные ряды, статистика)
- Поддержка ML-модулей через API

---

## 3. High-Level Architecture
Диаграмма или текстовое описание:
- **PostgreSQL (db)** – хранение событий, метаданных
- **FastAPI (api)** – REST API для ingestion, graph, analytics
- **ML Stub (ml_stub)** – прототип ML-сервисов (дедупликация, классификация)
- **Neo4j/Redis (позже)** – для графового анализа и кэша

---

## 4. Data Flow
1. Источники данных → `/ingest`
2. Запись в PostgreSQL (с provenance-логикой)
3. Аналитика через `/analytics`
4. Вызовы ML-модулей через `/ml_stub`

---

## 5. Module Description
### 5.1 API Service
- FastAPI
- Эндпоинты:
  - `/ingest` – приём событий
  - `/events` – выборка сырых событий
  - `/graph` – графовые представления
  - `/analytics` – агрегаты и отчёты

### 5.2 ML Stub
- Flask API
- Mock ML endpoints
- В дальнейшем заменяется на реальные модели

### 5.3 Database
- PostgreSQL
- Основные таблицы:
  - `events`
  - `entities`
  - `provenance`

---

## 6. Roadmap
- [x] Docker Compose (db, api, ml_stub)
- [ ] Интеграция Neo4j
- [ ] ML-модули (дедупликация, кластеризация)
- [ ] Визуальная аналитика

---

## 7. Open Questions
- Как хранить provenance: отдельная таблица или встроенные поля?
- Нужна ли message queue между ingestion и analytics?
- Требуется ли отдельный слой авторизации/аутентификации?

