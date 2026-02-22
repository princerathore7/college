from bson import ObjectId

def serialize_doc(doc):
    doc["_id"] = str(doc["_id"])
    return doc

def serialize_list(docs):
    return [serialize_doc(doc) for doc in docs]