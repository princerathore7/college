# backend/firebase_init.py
import os, json, firebase_admin
from firebase_admin import credentials

firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

if firebase_json:
    try:
        cred_dict = json.loads(firebase_json)
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully")
    except Exception as e:
        print("❌ Firebase init failed:", e)
else:
    print("⚠️ Firebase disabled: FIREBASE_SERVICE_ACCOUNT_JSON not set")
# firebase_init.py
def init_firebase():
    import os, json, firebase_admin
    from firebase_admin import credentials

    firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if firebase_json:
        cred_dict = json.loads(firebase_json)
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully")
    else:
        print("⚠️ Firebase disabled: FIREBASE_SERVICE_ACCOUNT_JSON not set")
