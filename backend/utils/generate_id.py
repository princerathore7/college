import random
import string

def generate_id(prefix="ID"):
    random_part = ''.join(random.choices(string.digits, k=6))
    return f"{prefix}{random_part}"