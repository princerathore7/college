from pymongo import MongoClient
from firebase_admin import messaging
import os

client = MongoClient(os.getenv("MONGO_COLLEGE_DB_URI"))
db = client["college_db"]

tokens_col = db["fcm_tokens"]

def push_notification(title, body, url, user_filter=None):
    query = user_filter or {}

    tokens = [t.get("token") for t in tokens_col.find(query) if t.get("token")]

    if not tokens:
        return {"status": "no_tokens"}

    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body
        ),
        data={"url": str(url)},
        tokens=tokens
    )

    response = messaging.send_multicast(message)

    return {
        "success": response.success_count,
        "failure": response.failure_count
    }
