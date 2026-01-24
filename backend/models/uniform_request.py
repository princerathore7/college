# models/uniform_request.py
from datetime import datetime
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["schoolDB"]

uniform_requests = db["uniform_requests"]

def create_uniform_request(data):
    data["status"] = "Pending"
    data["created_at"] = datetime.utcnow()
    return uniform_requests.insert_one(data)

def get_all_requests():
    return list(uniform_requests.find())

def update_status(request_id, new_status):
    return uniform_requests.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {"status": new_status}}
    )
