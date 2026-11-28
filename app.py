
import os
from flask import Flask, jsonify
from sheets_readonly import verify_schema

app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify(
        status="ok",
        service="ai-project-assistant",
        sheets_connected=False,
        writes_enabled=False
    )

@app.get("/")
def index():
    return jsonify(
        service="ai-project-assistant",
        mode="read-only-verification",
        writes_enabled=False
    )

@app.get("/verify-sheets")
def verify_sheets():
    try:
        result = verify_schema()
        return jsonify(result)
    except Exception:
        app.logger.exception("Google Sheets verification failed")
        return jsonify(
            status="error",
            reason="Verification failed. Check Render logs."
        ), 500

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000"))
    )
