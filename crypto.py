from cryptography.fernet import Fernet
from config import SECRET_KEY

fernet = Fernet(SECRET_KEY.encode())

def encrypt(text: str) -> str:
    return fernet.encrypt(text.encode()).decode()

def decrypt(text: str) -> str:
    return fernet.decrypt(text.encode()).decode()
