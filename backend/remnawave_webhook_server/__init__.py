# Remnawave Webhook Server Package
import sys
from pathlib import Path

# Add bot directory to sys.path during package initialization so that
# submodules can import mvm_bot at the very start of their files.
bot_dir = Path(__file__).resolve().parent.parent / "bot"
if str(bot_dir) not in sys.path:
    sys.path.insert(0, str(bot_dir))
