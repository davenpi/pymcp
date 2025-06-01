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
