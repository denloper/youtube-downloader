from messenger_ai.app import create_app
from messenger_ai.config import get_settings

import uvicorn


def main() -> None:
    settings = get_settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
