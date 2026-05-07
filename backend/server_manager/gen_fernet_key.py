"""Print a new Fernet key for SERVER_MANAGER_FERNET_KEY.

Does not load app settings — safe to run before .env is complete.

Usage:
  python -m server_manager.gen_fernet_key
"""

from cryptography.fernet import Fernet


def main() -> None:
    print(Fernet.generate_key().decode("ascii"))


if __name__ == "__main__":
    main()
