"""Content-addressed integrity: verify a file is byte-exact to a recorded hash, and keep the
correct bytes in a store named by that hash so recovery is a fetch, not a guess.

A file's correct identity is the hash of its correct bytes. The store (`store.py`) holds bytes
under their own sha256, git-object shaped and immutable, so it can never hold wrong bytes under a
right name and identical content dedupes for free. The `content-address` reconciler check verifies;
`recover` (a later, gated apply step) restores. Value-blind throughout: it proves bytes equal a
recorded hash, it never interprets what the bytes mean.
"""
