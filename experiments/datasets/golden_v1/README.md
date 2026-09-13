# golden_v1

`golden_v1` is the frozen native schema for the 45 held-out annotations.  It stores only the
semantic target-evaluation contract: claims plus exact `(claim_id, entity_id)` classifications.
`source.text` is retained solely to ground and validate evidence text; do not add old presentation
or document-level stance objects.  The original `golden_v0` files remain immutable and are loaded
only through the deterministic legacy adapter.
