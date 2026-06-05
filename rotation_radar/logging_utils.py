from __future__ import annotations


def format_status_message(message: str) -> str:
    return str(message)


def format_warning_message(message: str) -> str:
    text = str(message)
    if text.startswith("Warning: "):
        return text
    return f"Warning: {text}"


def log_status(message: str, *, end: str = "\n") -> None:
    print(format_status_message(message), end=end)


def log_warning(message: str, *, end: str = "\n") -> None:
    print(format_warning_message(message), end=end)
