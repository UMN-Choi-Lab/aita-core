# Module-level storage for OAuth PKCE code_verifiers, keyed by the OAuth `state`
# that Google echoes back on the redirect. Imported modules persist across
# Streamlit reruns and are shared by every session in the process, so a single
# global verifier would be overwritten by whichever student loaded the login
# page last (2026-11-02 claim rush: invalid_grant for nearly everyone).
verifiers = {}
_MAX = 2000  # ponytail: drop oldest past this; abandoned logins never return


def put(state, verifier):
    verifiers[state] = verifier
    while len(verifiers) > _MAX:
        verifiers.pop(next(iter(verifiers)))


def pop(state):
    return verifiers.pop(state, None) if state else None
