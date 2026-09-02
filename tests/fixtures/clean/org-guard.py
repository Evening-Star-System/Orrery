import re

# Account lowercase here on purpose; the source of truth uses mixed case. The
# reconciler compares accounts case-insensitively, so this must read as agreement.
BUCKET_ACCT = {
    "acme": ("codeberg.org", "acme"),
    "globex": ("github.com", "globex-inc"),
    "initech": ("github.com", "globex-inc"),
    "umbrella": ("github.com", "umbrella"),
}
_ = re
