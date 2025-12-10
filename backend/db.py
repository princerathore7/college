from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017"  # ya apna MongoDB URI
client = MongoClient(MONGO_URI)
db = client.college_db

print("MongoDB connected successfully")
