# Service and safety model

## Public boundary

The integration has one config entry and exactly six public services. Query
services always return a response. Start, cancel, and single-address test
services return one when the caller requests it, matching Home Assistant's
optional-response convention.

User-context calls require an administrator. Context-free internal service calls
are allowed. This policy is enforced before coordinator access.

## Validation

Service schemas accept exact integers or base-10 integer strings, then enforce
Modbus and timing bounds. Floats and booleans are rejected as numeric values.
`start_scan` requires the exact boolean `true` safety acknowledgement. The model
revalidates values for direct Python callers. Provider emissions pass a third,
adversarial validation boundary before entering state.

## State and races

A scan is scheduled as a non-eager Home Assistant task and returns immediately.
The coordinator records active ownership before task creation is exposed. Its
`finally` block releases ownership, timestamps the terminal state, records
bounded history, and removes the task reference. Shutdown covers both started
coroutines and non-eager tasks cancelled before startup.

A cancelled waiter does not cancel the underlying scan because waits are
shielded. Cooperative service cancellation sets a flag observed between mock
transactions. Unload performs hard task cancellation and awaits cleanup.

## Result meaning

Responder evidence includes identified responses, generic valid responses,
CRC-valid protocol exceptions, and possible collisions. Gateway errors are
retained but are not responders. Timeouts are fully counted but not retained as
records. Responses explicitly state `best_effort: true` and
`uniqueness_guaranteed: false`.
