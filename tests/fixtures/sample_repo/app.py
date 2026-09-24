class User:
    def __init__(self, uid: str, name: str) -> None:
        self.uid = uid
        self.name = name


def fetch_user(uid: str) -> User:
    return User(uid=uid, name="test")


def process(user: User) -> None:
    print(f"processing {user.name}")


def handle_login(uid: str) -> None:
    user = fetch_user(uid)
    process(user)
