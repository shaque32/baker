"""Training generator for Baker's stance model. every name, number and chat is invented.

Labels come by construction (eval/stancedata/families.py and LABELING_GUIDE.md): a scenario
picks a family, writes a chat excerpt and an assumption that fit its rule, and the family fixes
the stance. Wording lives here and only here, so the held-out generator shares none of it.
"""
