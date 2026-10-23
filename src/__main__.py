"""`python -m tiktok_transcriber` from an installed package."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import run  # noqa: E402

run()
