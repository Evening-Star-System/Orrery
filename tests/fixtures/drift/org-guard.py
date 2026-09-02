import re

# The historical drift: globex mapped to the personal account instead of the org.
BUCKET_ACCT = {
    "acme": ("codeberg.org", "acme"),
    "globex": ("github.com", "personal-fork"),
    "initech": ("github.com", "globex-inc"),
    "umbrella": ("github.com", "umbrella"),
    "ghost": ("github.com", "nowhere"),
}
_ = re
