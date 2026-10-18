from uuid import uuid4

CONFIGS = {
    "telegram": {
        "base_url": "https://notify.example.invalid",
        "bot_token": "123456:synthetic-secret",
        "chat_id": "-100123",
    },
    "bark": {"base_url": "http://192.168.1.2:8080/bark", "device_key": "synthetic-device-secret"},
    "webhook": {
        "response_mode": "status",
        "url": "https://notify.example.invalid/hook?key=synthetic-url-secret",
        "headers": {"Authorization": "Bearer synthetic-header-secret"},
    },
    "smtp": {
        "host": "mail.example.invalid",
        "username": "synthetic-user",
        "password": "synthetic-password",
        "from_address": "sender@example.invalid",
        "to_address": "recipient@example.invalid",
    },
}


def payload():
    return {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "post": {
            "website_id": "nodeseek",
            "external_post_id": "9002",
            "title": "<b>合成消息</b> & VPS",
            "summary": "synthetic summary",
            "author": "synthetic author",
            "category": "synthetic category",
            "url": "https://www.nodeseek.com/post-9002-1",
            "published_at": "2026-10-18T00:00:00+00:00",
            "first_seen_at": 20,
        },
        "matched_tasks": [{"id": str(uuid4()), "version": 1, "name": "synthetic rule"}],
    }
