from typing import Annotated, Any, Literal

from mcp.protocol.base import Notification, Request

LoggingLevel = Annotated[
    Literal[
        "debug",
        "info",
        "notice",
        "warning",
        "error",
        "critical",
        "alert",
        "emergency",
    ],
    "Level of logging the client wants to receive from the server.",
]


class SetLevelRequest(Request):
    """
    Request client sends to server to set/update the logging level.

    The server should send all logs at `level` and more severe.
    """

    method: Literal["logging/setLevel"] = "logging/setLevel"
    level: LoggingLevel
    """
    Client requests logs at this level and more severe.
    """


class LoggingMessageNotification(Notification):
    """
    Logging noticiation sent from server to client.

    If the client didn't set a logging level, the server can decide which messages to
    send automatically.
    """

    method: Literal["notifications/message"] = "notifications/message"
    level: LoggingLevel
    """
    Severity of the log message.
    """

    logger: str | None = None
    """
    Name of the logger issuing the message.
    """

    data: Any
    """
    Any JSON serializable data to log.
    """
