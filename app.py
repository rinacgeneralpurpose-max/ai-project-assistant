import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.get('/health')
def health():
    return jsonify(status='ok', service='ai-project-assistant', sheets_connected=False, writes_enabled=False)

@app.get('/')
def index():
    return jsonify(service='ai-project-assistant', mode='deployment-scaffold', sheets_connected=False, writes_enabled=False)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '10000')))
