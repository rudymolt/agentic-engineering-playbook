# Historical delivery regression fixture

`legacy-escalated-history.json` is a completed disposable repair/Verify history
produced and validated by public base `a57af6de259d34e9b772105e0ad0610290797cfa`.
Its two disposable remote locators were replaced with the public placeholder
`https://example.invalid/approved.git`, and the immutable approval digest was
recomputed before freezing and revalidating this public fixture against that
base. It contains no private project or machine records.

The frozen approval has no explicit `routes.escalated_verify`. Its literal
historical GPT-6 Sol/high operations, retries and execution evidence must stay
readable and resumable without migration. Tests validate the retained bytes,
approval binding and old routes directly, rather than regenerating history
using the current resolver. They also refuse forged or weaker operation routes.
