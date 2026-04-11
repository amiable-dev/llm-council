# Bug Fix Implementation Plan - BUG-023

## Problem Statement
The modularization of the council pipeline broke the public API of `run_full_council`. This regression prevents the CLI and HTTP server from functioning, as they rely on specific parameter names and return structures that were altered without corresponding updates to the callers.

## First Principles Analysis
1. **Contract Integrity**: A public API's signature is a contract. If the contract changes without a version bump or caller synchronization, the system enters an inconsistent state.
2. **Backward Compatibility**: In modular refactors, the "Facade" (orchestrator) should hide the underlying structural changes. The external interface must remain stable while the internal implementation evolves.
3. **Type Safety**: Python's dynamic nature allows for invisible signature changes, but runtime failures (`TypeError`) occur immediately upon invocation if keyword arguments mismatch.

## Proposed Strategy
1. **Restore Parameter Name**: Add `models` back to the `run_full_council` signature. To support the new `council_models` internal naming, we will use `models` as the external name and map it internally.
2. **Restore Return Signature**: Revert the tuple order to `(stage1_results, stage2_results, stage3_result, metadata)`.
3. **Enrich Metadata**: Ensure the `metadata` dictionary contains all the new data (rankings, labels, usage) so no information is lost by reverting the signature.
4. **Integration Testing**: Add a dedicated integration test that simulates CLI/HTTP-style calls to prevent future regressions of this core contract.

## Technical Details
- Update `src/llm_council/council.py`:
    - Change `council_models` back to `models`.
    - Modify the return statement to pack the 4 legacy variables.
    - Update `run_council_with_fallback` to destructure the restored 4-tuple.
