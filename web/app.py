"""FastAPI application factory."""
import asyncio
from pathlib import Path
from typing import Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from web.auth import require_auth, set_api_key
from web.websocket_manager import ws_manager, live_broadcaster, signals_broadcaster
from web.overview_scanner import run_overview_scanner
from web.routers import dashboard, positions, trades, signals, sentiment, bot_control, settings as settings_router, chart, coin as coin_router


def create_web_app(engine: Any) -> FastAPI:
    api_key = engine.settings.web_api_key
    set_api_key(api_key)

    app = FastAPI(
        title="BorsaBot Web API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Inject engine into routers
    for router_module in [dashboard, positions, trades, signals, sentiment, bot_control, settings_router, chart, coin_router]:
        router_module._engine = engine

    # Include routers (all protected by require_auth dependency)
    auth_dep = [Depends(require_auth)]
    app.include_router(dashboard.router, prefix="/api", dependencies=auth_dep)
    app.include_router(positions.router, prefix="/api", dependencies=auth_dep)
    app.include_router(trades.router, prefix="/api", dependencies=auth_dep)
    app.include_router(signals.router, prefix="/api", dependencies=auth_dep)
    app.include_router(sentiment.router, prefix="/api", dependencies=auth_dep)
    app.include_router(bot_control.router, prefix="/api", dependencies=auth_dep)
    app.include_router(settings_router.router, prefix="/api", dependencies=auth_dep)
    app.include_router(chart.router, prefix="/api", dependencies=auth_dep)
    app.include_router(coin_router.router, prefix="/api", dependencies=auth_dep)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.websocket("/ws/live")
    async def ws_live(websocket: WebSocket):
        # Auth via query param or header
        token = websocket.query_params.get("token", "")
        if api_key and token != api_key:
            await websocket.close(code=4001)
            return
        await ws_manager.connect_live(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect_live(websocket)

    @app.websocket("/ws/signals")
    async def ws_signals(websocket: WebSocket):
        token = websocket.query_params.get("token", "")
        if api_key and token != api_key:
            await websocket.close(code=4001)
            return
        await ws_manager.connect_signals(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect_signals(websocket)

    @app.on_event("startup")
    async def _start_broadcasters():
        asyncio.create_task(live_broadcaster(engine))
        asyncio.create_task(signals_broadcaster(engine))
        asyncio.create_task(run_overview_scanner(engine))

    # Serve React build (production only — frontend/dist must exist)
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            index = frontend_dist / "index.html"
            return FileResponse(str(index))

    return app
