import random
import string


# ---------------- SIMPLE VERIFICATION CODE ----------------

def generate_verification_code():

    letters = ''.join(
        random.choices(string.ascii_uppercase, k=3)
    )

    numbers = ''.join(
        random.choices(string.digits, k=3)
    )

    return letters + numbers


# ---------------- ADVANCED CODE GENERATOR ----------------

def generate_secure_code(length=8):

    characters = (
        string.ascii_uppercase +
        string.digits
    )

    secure_code = ''.join(
        random.choice(characters)
        for _ in range(length)
    )

    return secure_code


# ---------------- NUMERIC OTP ----------------

def generate_numeric_otp(length=6):

    otp = ''.join(
        random.choices(string.digits, k=length)
    )

    return otp


# ---------------- TESTING ----------------

if __name__ == "__main__":

    print("Simple Code:")
    print(generate_verification_code())

    print("\nSecure Code:")
    print(generate_secure_code())

    print("\nNumeric OTP:")
    print(generate_numeric_otp())