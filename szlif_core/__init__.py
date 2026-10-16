import os

__version__ = "0.2.0"
# How the user starts Szlif on this system, for the hints in messages.
COMMAND = "py szlif.py" if os.name == "nt" else "python3 szlif.py"
