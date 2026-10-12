# Held-out test split log

Every scoring of a candidate model on the held-out test split (ids H...) is one line here, as
GO_BAR.md requires. Dev-split runs are not logged. After three candidates the test split is
retired and regenerated from a new seed.

| date | candidate | model SHA-256 | training file SHA-256 | held-out SHA-256 | result |
|---|---|---|---|---|---|
