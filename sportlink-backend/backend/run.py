"""Local entrypoint: python -m backend.run"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "backend.app:app",
        host=os.getenv("SOLOPILOT_HOST", "127.0.0.1"),
        port=int(os.getenv("SOLOPILOT_PORT", "8100")),
        reload=os.getenv("SOLOPILOT_RELOAD", "false").lower() == "true",
        log_level=os.getenv("SOLOPILOT_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
