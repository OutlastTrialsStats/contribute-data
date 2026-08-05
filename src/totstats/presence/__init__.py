"""Discord Rich Presence: what you are playing, on your Discord profile.

Reads the same game log the contribute feature does and pushes a status to the local Discord
client. See doc/ for the log formats this relies on.
"""

from __future__ import annotations

# The Discord application this app publishes as. Discord shows its *name* after "Playing", so the
# application has to be registered as The Outlast Trials. Empty means unconfigured: the feature
# then parses and renders as usual but never opens a connection.
DISCORD_CLIENT_ID = "1529896965075370177"
