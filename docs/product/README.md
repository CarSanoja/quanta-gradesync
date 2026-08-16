# Product Documentation

Living documentation for the AutoCurricula & GradeSync Engine, written to
open-source documentation standards (DIATAXIS-style separation, status headers,
cross-references, honest limits).

| Document | Purpose | Audience |
|---|---|---|
| [How the GradeSync Engine Works — A Cold Run](how-it-works.md) | Detailed, current explanation of the architecture and the full life of a job | Engineers |
| [The GradeSync Engine as a Product](product-overview.md) | Value proposition, inputs/outputs, guarantees, ROI, limits, roadmap | Leadership, IT, evaluators |

## Update policy

These documents are **release artifacts, not historical records**:

1. Every implementation cycle **must** update both documents to match the shipped
   behavior (update the `Last updated` header to the cycle it reflects).
2. Historical context belongs in the [dev log (bitácora)](../bitacora/README.md),
   which is append-only; product docs describe only the *current* state.
3. Claims in these documents must be backed by shipped behavior — every guarantee
   cited here maps to a test in the suite.
