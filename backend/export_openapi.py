import json

from .app import create_app
from .config import PROJECT_ROOT, Settings

path = PROJECT_ROOT / "work/openapi.json"
path.parent.mkdir(exist_ok=True)
# Schema generation does not run lifespan hooks or touch the database.
path.write_text(json.dumps(create_app(Settings()).openapi(), indent=2) + "\n")
print(f"Exported {path}")
