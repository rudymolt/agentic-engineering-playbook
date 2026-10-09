# Verifier performance spec

The tracker issue holds the detailed requirements, baseline measurements, and acceptance criteria. Its five slices are ordered and each ships in a separate PR.

1. Split the 154 reviewed guidance tests into three balanced files, with fixture methods in a non-test module.
2. Remove accidental duplicate unittest discovery and inherited reruns.
3. Pass `--jobs` through to the delivery verifier when parallel verification is requested.
4. Keep full library matrices while sampling the CLI seam in heavy public tests.
5. Cache repeated product work within safe freshness boundaries.

Each PR must retain all tests and required CI jobs, include its own measurement evidence, update the changelog with a *Why* line, regenerate affected files, and pass the final full verifier.
