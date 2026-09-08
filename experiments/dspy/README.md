# DSPy experiments

This directory is reserved for offline DSPy work after `golden_v0` has a stable annotation schema.
The first pipeline should compose entity extraction and resolution, per-entity stance, atomic claim
extraction, attribution/modality, and rhetorical-feature detection. It must be evaluated against
the versioned golden dataset with a weighted component metric, not subjective prompt quality.

Store source code and metric definitions in Git. Track run outputs, cached predictions, and any
model artifacts through DVC.
