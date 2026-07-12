# Selector Core Unit Tests

This directory verifies strict common configuration, neutral records and protocols, correlation
logging, CWD-independent paths, and the Core vocabulary boundary.

Task 12 adds injected fake end-to-end accept/reject paths for both branch identities, resume from a
persisted generation, wrong-model-type rejection before run creation, and explicit failure
accounting. Core tests must use neutral fakes and must not import either Selector branch.
