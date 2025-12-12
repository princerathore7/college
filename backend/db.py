from pymongo import MongoClient
import os

# --------------------------------------------------------
# 🔥 1. Always load MongoDB URI from Environment Variable
# --------------------------------------------------------
# On production (Render), MONGO_URI MUST be set in environment
MONGO_URI = os.getenv("MONGO_URI")

# --------------------------------------------------------
# 🔄 2. If NO env variable found → fallback to local
# --------------------------------------------------------
if not MONGO_URI:
    print("⚠️ WARNING: MONGO_URI not found. Using LOCAL MongoDB...")
    MONGO_URI = "mongodb://localhost:27017"

else:
    print("✅ Loaded MongoDB URI from environment (Production Mode)")


# --------------------------------------------------------
# 🚀 3. Connect to MongoDB (Atlas or Local)
# --------------------------------------------------------
try:
    client = MongoClient(MONGO_URI)
    db = client["college_db"]  # Database auto-creates if not exist
    print("✅ MongoDB connected successfully")
except Exception as e:
    print("❌ MongoDB connection failed:", str(e))
    raise e
