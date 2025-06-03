# Forked May 30, 2025

## Types

- Starting to rewrite the types to feel more Pythonic and leaning on Pydantic

## Metadata

- Getting opinionated about metadata. It's very generic in the spec for extensibility.

- That means we can't be explicit in the SDK.

- Including metadata at that same level of generality creates more baggage for users.
Then they need to think through, what goes in here? When should I use it? How does it
interact with other fields? And so on.

- The point is to make an intuitive API that means users don't have to be protocol
experts. We're spec compliant over the wire, and if we don't support every single
metadata edge case, that's fine.

- When specific metadata use cases arise, support them explicitly. Otherwise we can
encourage users to send logging notifications or something else more explicit.

## Errors

- Getting opinionated about `Error` data. Right now the spec says:

```typescript
export interface JSONRPCError {
  jsonrpc: typeof JSONRPC_VERSION;
  id: RequestId;
  error: {
    /**
     * The error type that occurred.
     */
    code: number;
    /**
     * A short description of the error. The message SHOULD be limited to a concise single sentence.
     */
    message: string;
    /**
     * Additional information about the error. The value of this member is defined by the sender (e.g. detailed error information, nested errors etc.).
     */
    data?: unknown;
  };
}
```

zero guidance on what `data` should be. Kind of confusing for me and users. What should
I put there?

Clear that `data` description was taken from JSON RPC 2.0 spec. THe thing is—we're not
building a general JSON RPC library, we're just using that for transport. Let's try
to get more concrete about this based on usage. Understandable that they didn't have
much to go off of when writing the spec.
