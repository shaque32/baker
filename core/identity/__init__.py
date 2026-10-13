"""Identity audit: who is behind each account, as links the expert confirms or rejects.

Code proposes a link between an account and a person only where the extraction itself puts a
form of the person's name on that account (a saved contact, an account name, a thread title,
the sender text a report printed, the letters of a handle). It never uses a model, never
merges anything and never confirms anything. Proposed links only widen what the audit
searches for a person; checks count a link only once an expert confirms it
(core/audit/checks/_common.py person_party), and every report lists each confirmed link as a
limitation. See core/identity/links.py.
"""
