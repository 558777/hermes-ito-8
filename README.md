# hermes-ito-8

Лёгкий 8-лотовый распределитель «Гермес ITO» для Cloud.ru Evolution Container Apps.

Слушает `0.0.0.0:$PORT` (по умолчанию 8080), без внешних веб-фреймворков —
только stdlib + `boto3` для Object Storage.

## Лотки

| id | лоток | о чём |
|---|---|---|
| diamond | Алмаз | технологии, ИИ, наука, прорывы |
| platinum | Платина | логистика, порты, ж/д, фрахт |
| gold | Золото | эксклюзив владельцу: сделки, капитал, риски |
| silver | Серебро | рынки, курсы, ставки, регуляторика |
| brics | БРИКС-сырьё | уголь, металлы, нефть, газ, ЕАЭС |
| corridors | Коридоры и фрахт | маршруты, тарифы, перевозки |
| law | Право и комплаенс | законы, суды, лицензии, пошлины |
| nuggets | Самородки Владельцу | аномалии, инсайды, находки |

## API

- `GET /health` — живость, наличие ключей;
- `GET /lots` — список лотков;
- `GET /models` — первые модели Foundation Models;
- `POST /classify` — `{"text": "..."}` → лоток по правилам;
- `POST /digest` — `{"text": "...", "model": "..."}` → сводка модели + запись в S3.

## Переменные окружения

| переменная | назначение |
|---|---|
| `PORT` | порт (по умолчанию 8080) |
| `CLOUDRU_API_KEY` | ключ Foundation Models |
| `CLOUDRU_BASE_URL` | по умолчанию `https://foundation-models.api.cloud.ru/v1` |
| `S3_ACCESS_KEY` | `<tenant_id>:<key_id>` |
| `S3_SECRET_KEY` | секрет S3-ключа |
| `S3_BUCKET` | `ito-hermes-mirror` |
| `S3_ENDPOINT` | `https://s3.cloud.ru` |
| `S3_REGION` | `ru-central-1` |

## Сборка

```bash
docker build -t hermes-ito:v1 .
docker run -p 8080:8080 -e CLOUDRU_API_KEY=... -e S3_ACCESS_KEY=... -e S3_SECRET_KEY=... hermes-ito:v1
```

Секреты в репозиторий не кладутся — только через переменные окружения Container App.
