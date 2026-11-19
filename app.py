# -*- coding: utf-8 -*-
"""hermes_ito_8.py — лёгкий 8-лотовый распределитель «Гермес ITO».

Контуры:
  * Foundation Models Cloud.ru (https://foundation-models.api.cloud.ru/v1) —
    GigaChat / DeepSeek / Qwen через OpenAI-совместимый chat/completions;
  * Object Storage Cloud.ru (https://s3.cloud.ru, ru-central-1) — сливки в
    bucket ito-hermes-mirror, префикс hermes8/;
  * HTTP API на 0.0.0.0:8080 (stdlib, без внешних веб-фреймворков):
      GET  /health          — живость и режим;
      GET  /lots            — список восьми лотков;
      POST /classify        — {"text": "..."} -> лоток по правилам;
      POST /digest          — {"text": "...", "model": "..."} -> сводка модели
                              + запись в S3 (ключ hermes8/YYYY-MM-DD/*.json).

Секреты — только из переменных окружения (в контейнере их даёт Container App):
  CLOUDRU_API_KEY, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET, S3_ENDPOINT, S3_REGION.
NO_FINANCIAL_SIGNING=1, наружу секреты не отдаются, в логи не пишутся.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_BASE = os.environ.get("CLOUDRU_BASE_URL", "https://foundation-models.api.cloud.ru/v1")
API_KEY = os.environ.get("CLOUDRU_API_KEY", "").strip()
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "https://s3.cloud.ru")
S3_REGION = os.environ.get("S3_REGION", "ru-central-1")
S3_BUCKET = os.environ.get("S3_BUCKET", "ito-hermes-mirror")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "").strip()
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "").strip()
PORT = int(os.environ.get("PORT", "8080"))
TZ = timezone.utc

LOTS = [
    ("diamond", "Алмаз", "прорывные технологии, ИИ, наука, стратегические решения"),
    ("platinum", "Платина", "логистика, порты, железные дороги, фрахт, коридоры"),
    ("gold", "Золото", "эксклюзив владельцу: крупные сделки, капитал, риски"),
    ("silver", "Серебро", "рынки, курсы, ставки, регуляторика, статистика"),
    ("brics", "БРИКС-сырьё", "уголь, металлы, нефть, газ, удобрения, ЕАЭС/БРИКС"),
    ("corridors", "Коридоры и фрахт", "маршруты, тарифы, ставки фрахта, пробки, санкции на транспорте"),
    ("law", "Право и комплаенс", "законы, суды, лицензии, сертификация, пошлины, штрафы"),
    ("nuggets", "Самородки Владельцу", "нестандартные находки, инсайды, аномалии рынка"),
]

RULES = {
    "law": ("суд", "закон", "лиценз", "сертифик", "пошлин", "штраф", "комплаенс",
            "регулятор", "запрет", "антимонопол", "ndt", "патент"),
    "corridors": ("фрахт", "контейнер", "порт", "железн", "ржд", "коридор", "тариф",
                  "рейс", "перевоз", "logistic", "freight", "shipping", "терминал"),
    "brics": ("уголь", "металл", "нефт", "газ", "удобрен", "еаэс", "брикс", "сырь",
              "медь", "никель", "алюмин", "сталь", "зерно"),
    "silver": ("курс", "ставк", "инфляц", "индекс", "биржа", "moex", "цб ", "рубл",
               "юан", "доллар", "статистик", "ввп"),
    "diamond": ("ии ", "искусственн", "технолог", "наук", "прорыв", "нейросет", "квант",
                "спутник", "полупроводник", "gpu"),
    "gold": ("сделк", "капитал", "акци", "ipo", "миллиард", "$", "инвест", "кризис",
             "риск", "дефолт"),
    "nuggets": ("аномал", "инсайд", "находк", "уник", "сенсац", "впервые"),
}


def classify(text):
    """Правила: >1 совпадения — лоток, иначе медиана по весам, иначе nuggets."""
    low = (" " + str(text or "").lower() + " ")
    scores = {}
    for lot, words in RULES.items():
        n = sum(1 for w in words if w in low)
        if n:
            scores[lot] = n
    if not scores:
        return {"lot": "silver", "name": dict((k, v) for k, _, v in LOTS)["silver"],
                "score": 0, "why": "нет маркеров — статистика по умолчанию"}
    lot = max(scores, key=scores.get)
    name = next(n for k, n, _ in LOTS if k == lot)
    return {"lot": lot, "name": name, "score": scores[lot],
            "why": "совпадений: %d" % scores[lot]}


def _api(method, path, payload=None, timeout=120):
    url = API_BASE.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": "Bearer " + API_KEY})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def models():
    try:
        data = _api("GET", "/models", timeout=25)
        return [m.get("id") for m in (data.get("data") or []) if m.get("id")]
    except Exception as e:
        return ["__error__: %s" % type(e).__name__]


def ask_model(prompt, model=None, max_tokens=700):
    """Сводка модели. Без явной модели — GigaChat, затем DeepSeek, затем Qwen."""
    if not API_KEY:
        return {"ok": False, "error": "CLOUDRU_API_KEY не задан"}
    chain = [model] if model else ["GigaChat/GigaChat-3-Pro",
                                   "deepseek-ai/DeepSeek-V4-Pro",
                                   "Qwen/Qwen3.5-397B-A17B"]
    last = "нет ответа"
    for m in chain:
        try:
            data = _api("POST", "/chat/completions",
                        {"model": m, "max_tokens": max_tokens, "temperature": 0.3,
                         "messages": [{"role": "user", "content": prompt}]}, timeout=150)
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            text = (msg.get("content") or "").strip()
            if text:
                return {"ok": True, "model": m, "text": text}
            last = "%s: пустой ответ" % m
        except urllib.error.HTTPError as e:
            last = "%s: HTTP %d" % (m, e.code)
            if e.code in (401, 403):
                break
        except Exception as e:
            last = "%s: %s" % (m, type(e).__name__)
    return {"ok": False, "error": last}


def _s3_put(key, body_bytes, content_type="application/json"):
    """PUT в Object Storage Cloud.ru через boto3 (в образе ставится pip)."""
    if not (S3_ACCESS_KEY and S3_SECRET_KEY):
        return {"ok": False, "error": "S3-ключи не заданы в окружении"}
    try:
        import boto3
        from botocore.config import Config
    except Exception as e:
        return {"ok": False, "error": "boto3 недоступен: %s" % e}
    try:
        cli = boto3.client(
            "s3", endpoint_url=S3_ENDPOINT, region_name=S3_REGION,
            aws_access_key_id=S3_ACCESS_KEY, aws_secret_access_key=S3_SECRET_KEY,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
        cli.put_object(Bucket=S3_BUCKET, Key=key, Body=body_bytes,
                       ContentType=content_type)
        return {"ok": True, "bucket": S3_BUCKET, "key": key, "bytes": len(body_bytes)}
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:160])}


class Handler(BaseHTTPRequestHandler):
    server_version = "HermesITO8/1.0"

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            return json.loads(raw.decode("utf-8", "replace") or "{}")
        except Exception:
            return {}

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send(200, {"ok": True, "service": "hermes-ito-8",
                                    "ts": datetime.now(TZ).isoformat(timespec="seconds"),
                                    "api_key": bool(API_KEY),
                                    "s3": bool(S3_ACCESS_KEY and S3_SECRET_KEY),
                                    "bucket": S3_BUCKET, "port": PORT})
        if self.path.startswith("/lots"):
            return self._send(200, {"lots": [{"id": k, "name": n, "about": a}
                                             for k, n, a in LOTS]})
        if self.path.startswith("/models"):
            return self._send(200, {"models": models()[:20]})
        return self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        data = self._body()
        text = str(data.get("text") or "").strip()
        if self.path.startswith("/classify"):
            if not text:
                return self._send(400, {"ok": False, "error": "empty text"})
            return self._send(200, {"ok": True, "classify": classify(text)})
        if self.path.startswith("/digest"):
            if not text:
                return self._send(400, {"ok": False, "error": "empty text"})
            lot = classify(text)
            prompt = ("Ты — Гермес ITO, распределитель по 8 лоткам. "
                      "Дай сжатую сводку 3–5 строк: цифры, факты, маршруты, риск. "
                      "Лоток: %s. Текст: %s" % (lot["name"], text[:3000]))
            res = ask_model(prompt, data.get("model"))
            stamp = datetime.now(TZ)
            key = "hermes8/%s/%s-%s.json" % (
                stamp.strftime("%Y-%m-%d"),
                stamp.strftime("%H%M%S"),
                hashlib.sha256(text.encode("utf-8")).hexdigest()[:8])
            payload = {"ts": stamp.isoformat(timespec="seconds"), "lot": lot,
                       "model": res.get("model"), "ok": res.get("ok"),
                       "digest": res.get("text") or res.get("error"),
                       "source_chars": len(text)}
            put = _s3_put(key, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return self._send(200 if res.get("ok") else 502,
                              {"ok": res.get("ok"), "lot": lot,
                               "model": res.get("model"),
                               "digest": payload["digest"], "s3": put})
        return self._send(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (datetime.now(TZ).strftime("%H:%M:%S"), fmt % args))


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write("hermes-ito-8 on :%d, api_key=%s, s3=%s\n"
                     % (PORT, bool(API_KEY), bool(S3_ACCESS_KEY and S3_SECRET_KEY)))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
