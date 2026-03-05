from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64
import json

def generate_vapid_keys():
    # private key generate karo
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # keys ko base64 me encode karo
    private_key_b64 = base64.urlsafe_b64encode(
        private_key.private_numbers().private_value.to_bytes(32, 'big')
    ).decode('utf-8')

    public_key_b64 = base64.urlsafe_b64encode(
        public_key.public_numbers().x.to_bytes(32, 'big')
    ).decode('utf-8')

    return {
        "publicKey": public_key_b64,
        "privateKey": private_key_b64
    }

vapid_keys = generate_vapid_keys()
print(json.dumps(vapid_keys, indent=4))