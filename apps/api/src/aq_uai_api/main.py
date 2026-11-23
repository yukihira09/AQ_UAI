"""Application entry point. Authentication and business APIs start in Phase 2/3."""

from fastapi import FastAPI

from aq_uai_api import __version__
from aq_uai_api.api.errors import install_error_handlers
from aq_uai_api.api.v1.auth import router as auth_router
from aq_uai_api.api.v1.directory import router as directory_router
from aq_uai_api.api.v1.system import router as system_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AQ EduUAI API",
        version=__version__,
        description="AQ EduUAI diagnostics, local authentication, and protected directory.",
    )
    install_error_handlers(app)
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(directory_router, prefix="/api/v1")
    return app


app = create_app()
