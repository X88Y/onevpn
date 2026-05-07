import firebase_admin
from firebase_admin import credentials, firestore

from server_manager.config import settings


def init_firestore() -> firestore.Client:
    if not firebase_admin._apps:
        path = settings.firebase_service_account_path
        if path:
            firebase_admin.initialize_app(credentials.Certificate(path))
        else:
            firebase_admin.initialize_app()
    return firestore.client()


VPN_SERVERS_COLLECTION = "vpn_servers"
VPN_CLIENTS_COLLECTION = "vpn_clients"
VPN_INSTALL_JOBS_COLLECTION = "vpn_install_jobs"
