"""FastAPI application factory and uvicorn runner for Dungeon Weaver."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.campaign.loader import load_campaign, load_srd_data

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dungeon Weaver Web Server")
    p.add_argument("--campaign", default="campaigns/shattered_crown",
                   help="Path to campaign (JSON or YAML directory)")
    p.add_argument("--provider", default="anthropic",
                   choices=["anthropic", "gemini", "ollama", "deepseek"],
                   help="LLM provider")
    p.add_argument("--model", default=None, help="Model name override")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--static", default=None,
                   help="Serve static frontend files from this directory")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def create_app(args: argparse.Namespace | None = None) -> FastAPI:
    if args is None:
        args = parse_args()

    # Set up logging
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("httpx", "httpcore", "urllib3", "google", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    app = FastAPI(title="Dungeon Weaver", version="0.1.0")

    # CORS for Vite dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Load SRD data and campaign at startup
    load_srd_data()
    logger.info("SRD data loaded")

    campaign_path = Path(args.campaign)
    if not campaign_path.exists():
        json_fallback = campaign_path.with_suffix(".json")
        if json_fallback.exists():
            campaign_path = json_fallback
        else:
            raise FileNotFoundError(f"Campaign not found: {campaign_path}")

    campaign = load_campaign(campaign_path)
    logger.info("Campaign loaded: %s", campaign.title)

    # Store config in app state
    app.state.campaign = campaign
    app.state.provider = args.provider
    app.state.model = args.model
    app.state.session = None
    app.state.debug = args.debug

    # Include routers
    from src.api.game_server import router as ws_router
    from src.api.routes.compendium import router as compendium_router
    from src.api.routes.session import router as session_router
    from src.api.routes.state import router as state_router

    app.include_router(session_router, prefix="/api")
    app.include_router(state_router, prefix="/api")
    app.include_router(compendium_router, prefix="/api")
    app.include_router(ws_router, prefix="/api")

    # Optionally serve static frontend build
    if args.static:
        from fastapi.staticfiles import StaticFiles
        static_dir = Path(args.static)
        if static_dir.is_dir():
            app.mount("/", StaticFiles(directory=str(static_dir), html=True))
            logger.info("Serving static files from %s", static_dir)

    return app


def main() -> None:
    import uvicorn
    args = parse_args()
    app = create_app(args)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
