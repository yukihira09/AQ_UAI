"""Application entry point. Authentication and business APIs start in Phase 2/3."""

import logging

from fastapi import FastAPI

from aq_uai_api import __version__
from aq_uai_api.api.errors import install_error_handlers
from aq_uai_api.api.v1.auth import router as auth_router
from aq_uai_api.api.v1.directory import router as directory_router
from aq_uai_api.api.v1.mdl import router as mdl_router
from aq_uai_api.api.v1.qta import router as qta_router
from aq_uai_api.api.v1.system import router as system_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AQ EduUAI API",
        version=__version__,
        description=(
            "AQ EduUAI diagnostics, local authentication, protected directory, "
            "and AI provider/model configuration."
        ),
    )
    install_error_handlers(app)
    # M4: httpcore (used only by the MDL connection test) logs provider response headers
    # at DEBUG. Provider text must never reach the logs (RULE-MDL-04), whatever the root
    # level an operator chooses.
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(directory_router, prefix="/api/v1")
    app.include_router(mdl_router, prefix="/api/v1")
    app.include_router(qta_router, prefix="/api/v1")
    return app


app = create_app()
