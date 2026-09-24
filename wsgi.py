import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app, socketio  # noqa: E402

app = create_app()

if __name__ == "__main__":
    # This entrypoint is for local development only. In production, run with
    # gunicorn (see README) - that doesn't go through this __main__ block.
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)
