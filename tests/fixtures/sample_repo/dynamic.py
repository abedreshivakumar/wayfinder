from app import fetch_user, process

HANDLERS = {"greet": lambda user: process(user)}


def dispatch(kind: str, uid: str) -> None:
    user = fetch_user(uid)
    HANDLERS[kind](user)


def never_called(uid: str) -> None:
    process(fetch_user(uid))


def run(uid: str) -> str:
    dispatch("greet", uid)
    return "done"
