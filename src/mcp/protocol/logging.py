"""
MCP Server Logging: Your window into what's happening behind the scenes.

Building an MCP application? Your server is doing important work—connecting to
databases, processing files, calling APIs—but when something goes wrong, you're flying
blind. That's where MCP's logging protocol comes in.

Think of it as a conversation between your client and server about visibility:

    Client: "I need to debug this. Show me what you're doing."
    Server: "How much detail do you want?"
    Client: "Start with errors, but I might need more if things get weird."
    Server: "Got it. Here's what's happening..."

The flow is simple but powerful:

1. **Request visibility**: Your client sends a `SetLevelRequest` to dial up the logging
2. **Stream insights**: The server responds with `LoggingMessageNotification`s as things
happen
3. **Adjust the firehose**: Change the level anytime to see more or less detail

The logging levels follow syslog severity (RFC 5424), from `debug` (everything) to
`emergency` (the server is on fire). Choose your level based on what you're trying to
solve:

- `error` and above: "Something's broken, show me what"
- `info` and above: "I want to see the server's major decisions"
- `debug`: "I need to see everything, performance be damned"

Pro tip: If you never send a `SetLevelRequest`, the server picks what to show you
automatically.
"""

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
    """
    Logging severity levels, following syslog standards (RFC 5424).
    
    When you set a level, you receive that level and all more severe levels.
    Common choices:
    - 'error': Only problems that need attention
    - 'info': Major server operations and errors  
    - 'debug': Everything (verbose, use sparingly)
    """,
]


class SetLevelRequest(Request):
    """
    Tell the server what level of logging detail you want to receive.

    Send this to start receiving log notifications at your chosen severity level
    and above. You can send multiple requests to adjust the level dynamically
    as your debugging needs change.
    """

    method: Literal["logging/setLevel"] = "logging/setLevel"
    level: LoggingLevel
    """
    The minimum severity level for log messages you want to receive.
    """


class LoggingMessageNotification(Notification):
    """
    A log message sent from server to client.

    These notifications stream server activity in real-time. Each message
    includes severity level, log data, and an optional logger name. If no logging level
    was set, the server chooses what to send automatically.
    """

    method: Literal["notifications/message"] = "notifications/message"
    level: LoggingLevel
    """
    Severity level of this log message.
    """

    logger: str | None = None
    """
    Name of the logger that generated this message (optional).
    """

    data: Any
    """
    The log payload - typically a string message or structured data.
    """
