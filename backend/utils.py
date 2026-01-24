import uuid
from datetime import datetime

def generate_id(prefix="ID"):
    return f"{prefix}-{uuid.uuid4().hex[:6]}"

def current_date():
    return datetime.utcnow().isoformat()
