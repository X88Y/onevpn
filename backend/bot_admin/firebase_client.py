import firebase_admin
from firebase_admin import credentials, firestore

from bot_admin.config import service_account_path


def init_firestore() -> firestore.Client:
    if not firebase_admin._apps:
        account_path = service_account_path()
        if account_path is not None:
            firebase_admin.initialize_app(credentials.Certificate(account_path))
        else:
            firebase_admin.initialize_app()
    return firestore.client()
