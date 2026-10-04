"""
Shared Flask extension instances.

Kept in their own module (rather than defined in app.py) so blueprint
files like auth.py and chat.py can import `limiter` to decorate their own
routes without a circular import: app.py imports the blueprints, so the
blueprints can't import the limiter back out of app.py.
"""
import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Storage defaults to in-memory, which is fine for a single web process
# but resets on restart and isn't shared across multiple gunicorn
# workers/dynos; set REDIS_URL (see the "Provision Redis" Implementation
# Checklist item) to back it with real shared storage once that's set up.
# Either way, this stops a script hammering one endpoint in a loop, which
# is the actual risk the CAPTCHA alone doesn't cover.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.environ.get("REDIS_URL", "memory://"),
    default_limits=[],
)
