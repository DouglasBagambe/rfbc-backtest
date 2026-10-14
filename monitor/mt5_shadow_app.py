"""Isolated SHADOW evidence service. No workers, Telegram, or production data."""
import os
from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from waitress import serve
import mt5_bridge

app=Flask(__name__)
if os.getenv('FX101_MT5_TRUST_PROXY','0')=='1': app.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1)
app.register_blueprint(mt5_bridge.bp)
@app.get('/health')
def health(): return jsonify(ok=True,build='mt5-v2-shadow',auto_available=False)
if __name__=='__main__':
    serve(app,trusted_proxy="*" if os.getenv("FX101_MT5_TRUST_PROXY","0")=="1" else None,
          trusted_proxy_headers={"x-forwarded-proto"} if os.getenv("FX101_MT5_TRUST_PROXY","0")=="1" else set(),host='0.0.0.0',port=int(os.getenv('PORT','10000')),threads=4,max_request_body_size=mt5_bridge.MAX_BYTES)
