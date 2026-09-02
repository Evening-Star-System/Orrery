"""Install lifecycle: in-place update, and backup/restore of the user's setup.

Everything here reads or writes the durable home from orrery.home, never the installed
package. `ess-orrery update` upgrades the code and, because setup lives outside the package,
wipes nothing by construction; backup/restore make that setup a portable artifact the
user owns.
"""
