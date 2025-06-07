from typing import Annotated, Literal

from pydantic import AnyUrl, UrlConstraints, field_validator

from mcp.protocol.base import Notification, ProtocolModel, Request, Result


class Root(ProtocolModel):
    """
    A root of the server.
    """

    uri: Annotated[AnyUrl, UrlConstraints(host_required=False)]
    """
    URI must start with file:// in this version of the protocol.
    """
    name: str | None = None

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: AnyUrl) -> AnyUrl:
        if not str(v).startswith("file://"):
            raise ValueError(
                "Root URI must start with file:// "
                "(current protocol version requirement)"
            )
        return v


class ListRootsRequest(Request):
    """
    Request to list the roots of the server.
    """

    method: Literal["roots/list"] = "roots/list"


class ListRootsResult(Result):
    """
    Response containing the roots of the server.
    """

    roots: list[Root]


class RootsListChangedNotification(Notification):
    """
    Notification that the roots of the server have changed.
    """

    method: Literal["notifications/roots/list_changed"] = (
        "notifications/roots/list_changed"
    )
