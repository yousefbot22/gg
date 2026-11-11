"""
Services package.

⚠️ Intentionally minimal — no eager imports.

Same rationale as src.solver: eager imports here cause circular imports
because session_manager → qureo_client → browser_pool → ...

Consumers should import from the specific module:
    from src.services.session_manager import session_manager
    from src.services.queue_manager import queue_manager
"""