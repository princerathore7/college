from pymongo import MongoClient
import os

# --------------------------------------------------------
# 🔥 1. Load MongoDB URI from Environment Variable
# --------------------------------------------------------
# Your environment variable name:
MONGO_URI = os.getenv("MONGO_COLLEGE_DB_URI")

# --------------------------------------------------------
# 🔄 2. Fallback to local MongoDB if ENV not found
# --------------------------------------------------------
if not MONGO_URI:
    print("⚠️ WARNING: MONGO_COLLEGE_DB_URI not found. Using LOCAL MongoDB...")
    MONGO_URI = "mongodb://localhost:27017"
else:
    print("✅ Loaded MongoDB URI from environment (Production Mode)")

# --------------------------------------------------------
# 🚀 3. Connect to MongoDB (Atlas or Local)
# --------------------------------------------------------
try:
    client = MongoClient(MONGO_URI)
    db = client["college_db"]  # Database auto-created if not exist
    print("✅ MongoDB connected successfully")
except Exception as e:
    print("❌ MongoDB connection failed:", str(e))
    raise e
