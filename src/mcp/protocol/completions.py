from typing import Annotated, Literal

from pydantic import Field

from mcp.protocol.base import ProtocolModel, Request, Result
from mcp.protocol.prompts import PromptReference
from mcp.protocol.resources import ResourceReference


class Completion(ProtocolModel):
    """
    Completion response containing multiple available options.
    """

    values: Annotated[list[str], Field(max_length=100)]
    total: int | None = None
    has_more: bool | None = Field(default=None, alias="hasMore")


class CompletionArgument(ProtocolModel):
    """
    Arguments for the completion request.
    """

    name: str
    value: str


class CompleteRequest(Request):
    """
    Request from client to server to ask for completion options.
    """

    method: Literal["completion/complete"] = "completion/complete"
    ref: PromptReference | ResourceReference
    argument: CompletionArgument


class CompleteResult(Result):
    completion: Completion
