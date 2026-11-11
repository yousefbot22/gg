"""
Solver package.

⚠️ Intentionally minimal — no eager imports.

Rationale:
    session_manager imports qureo_client, which lives here.
    If __init__ eagerly imported qureo_client, we'd get a circular import:

        session_manager → src.solver.qureo_client
                        → src.solver.__init__
                        → src.solver.qureo_client (circular!)

    Consumers must import from the specific module instead:
        from src.solver.qureo_client import QureoClient
        from src.solver.gemini_solver import GeminiSolver
        from src.solver.browser_pool import browser_pool
"""