# generate_vapid.py
from py_vapid import Vapid

v = Vapid()

keys = v.generate_keys()
if keys:
    print("Public Key:", keys.get("public"))
    print("Private Key:", keys.get("private"))
else:
    print("Key generation failed. Check py-vapid and cryptography versions.")
