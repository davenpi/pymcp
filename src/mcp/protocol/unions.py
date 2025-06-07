from mcp.protocol.common import (
    CancelledNotification,
    EmptyResult,
    PingRequest,
    ProgressNotification,
)
from mcp.protocol.completions import CompleteRequest, CompleteResult
from mcp.protocol.initialization import (
    InitializedNotification,
    InitializeRequest,
    InitializeResult,
)
from mcp.protocol.jsonrpc import (
    JSONRPCError,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from mcp.protocol.logging import LoggingMessageNotification, SetLevelRequest
from mcp.protocol.prompts import (
    GetPromptRequest,
    GetPromptResult,
    ListPromptsRequest,
    ListPromptsResult,
    PromptListChangedNotification,
)
from mcp.protocol.resources import (
    ListResourcesRequest,
    ListResourcesResult,
    ListResourceTemplatesRequest,
    ListResourceTemplatesResult,
    ReadResourceRequest,
    ReadResourceResult,
    ResourceListChangedNotification,
    ResourceUpdatedNotification,
    SubscribeRequest,
    UnsubscribeRequest,
)
from mcp.protocol.roots import ListRootsResult, RootsListChangedNotification
from mcp.protocol.sampling import CreateMessageRequest, CreateMessageResult
from mcp.protocol.tools import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    ToolListChangedNotification,
)

# ----------- Client Requests -------------
ClientRequest = (
    PingRequest
    | InitializeRequest
    | CompleteRequest
    | SetLevelRequest
    | GetPromptRequest
    | ListPromptsRequest
    | ListResourcesRequest
    | ListResourceTemplatesRequest
    | ReadResourceRequest
    | SubscribeRequest
    | UnsubscribeRequest
    | CallToolRequest
    | ListToolsRequest
)

# ----------- Client Notifications -------------
ClientNotification = (
    CancelledNotification
    | ProgressNotification
    | InitializedNotification
    | RootsListChangedNotification
)

# ----------- Client Results -------------
ClientResult = EmptyResult | CreateMessageResult | ListRootsResult

# ----------- Server Requests -------------
ServerRequest = PingRequest | CreateMessageRequest | ListToolsRequest

# ----------- Server Notifications -------------
ServerNotification = (
    CancelledNotification
    | ProgressNotification
    | LoggingMessageNotification
    | ResourceUpdatedNotification
    | ResourceListChangedNotification
    | ToolListChangedNotification
    | PromptListChangedNotification
)

# ----------- Server Results -------------
ServerResult = (
    EmptyResult
    | InitializeResult
    | CompleteResult
    | GetPromptResult
    | ListPromptsResult
    | ListResourceTemplatesResult
    | ListResourcesResult
    | ReadResourceResult
    | CallToolResult
    | ListToolsResult
)

# ---------- JSONRPC Messages -------------
JSONRPCBatchRequest = list[JSONRPCRequest | JSONRPCNotification]

JSONRPCBatchResponse = list[JSONRPCResponse | JSONRPCError]

JSONRPCMessage = (
    JSONRPCRequest
    | JSONRPCNotification
    | JSONRPCBatchRequest
    | JSONRPCResponse
    | JSONRPCError
    | JSONRPCBatchResponse
)
