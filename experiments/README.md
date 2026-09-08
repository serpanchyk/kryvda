# Experiments

This directory holds reproducible offline work that is not part of the production runtime.

- `datasets/` contains dataset definitions, annotation guidance, and DVC-tracked data.
- `dspy/` contains structured-extraction experiments and their evaluation artifacts.

Code, schemas, guidance, and DVC metadata are committed to Git. Dataset contents, run outputs,
and model artifacts are tracked by DVC and must not be added to Git directly.
