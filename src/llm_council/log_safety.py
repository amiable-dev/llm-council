"""Sanitize external strings before they are interpolated into log messages.

CWE-117: a value containing CR/LF can forge additional log lines when logged
verbatim (file paths, subprocess stderr, model identifiers, and exception text
can all carry them if the underlying content is attacker-influenced).
"""


def safe_log(value: object) -> str:
    """Return `value` as a string with CR/LF collapsed, safe to log verbatim."""
    return str(value).replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
