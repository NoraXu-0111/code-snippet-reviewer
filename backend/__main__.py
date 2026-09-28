import argparse
import os

import uvicorn

from .config import get_settings

parser = argparse.ArgumentParser()
parser.add_argument("--reload", action="store_true")
parser.add_argument("--serve-client", action="store_true")
args = parser.parse_args()
if args.serve_client:
    os.environ["SERVE_CLIENT"] = "true"
settings = get_settings()
uvicorn.run(
    "backend.app:app",
    host=settings.host,
    port=settings.port,
    reload=args.reload,
    reload_dirs=["backend"] if args.reload else None,
)
