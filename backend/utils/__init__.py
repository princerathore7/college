import random
import string
from .generate_id import generate_id
def generate_id(prefix):
    random_part = ''.join(random.choices(string.digits, k=6))
    return f"{prefix}{random_part}"