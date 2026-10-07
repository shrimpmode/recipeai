import logging

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}


class KeyValueFormatter(logging.Formatter):
    """Appends `extra={...}` fields as `key=value` pairs so context like
    `query_request_id` or `run_id` lands on the log line itself (greppable,
    and parseable by most log tools) instead of being silently dropped."""

    def formatMessage(self, record: logging.LogRecord) -> str:
        line = super().formatMessage(record)
        extras = {key: value for key, value in vars(record).items() if key not in _STANDARD_ATTRS}
        if not extras:
            return line
        return line + " " + " ".join(f"{key}={value!r}" for key, value in extras.items())
