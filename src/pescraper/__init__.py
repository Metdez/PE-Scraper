"""pescraper — Windows-native PE firm investment-criteria dataset pipeline.

Importing this package activates the Windows runtime hardening (asyncio Proactor
event-loop policy + UTF-8 stdio) as an import-time side effect, so every consumer
(CLI, smoke test, later workers) inherits the hardened runtime.
"""

from pescraper.runtime import configure_windows_runtime

configure_windows_runtime()

__version__ = "0.1.0"
