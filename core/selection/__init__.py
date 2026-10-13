"""Selection audit: what the government picked out of the extraction, and what it left around it.

picks.py   what was picked: words a government-document paragraph quotes, the messages Context
           Restore matched for each exhibit, and messages a report marks with an examiner tag
audit.py   each picked message in its own conversation: the messages exchanged with it that were
           not picked (just before, in between, just after), and the nearest ones outside

Derived by code from the case database each time it is shown. Nothing is stored, no model is
involved, and nothing here sets or changes a verdict. Findings are for the expert.
"""
