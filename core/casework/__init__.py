"""Starting and running a case from the review screen: case folders, file import, the
background audit and claim-proposal jobs, the model check and keeping the computer awake.

Nothing here makes a network call. Every change to the case goes through core/review/actions.py,
core/ingest/ or core/pipeline.py, so the audit log records it as it does from the command line.
"""
