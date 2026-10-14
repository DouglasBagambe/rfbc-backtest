"""Permanent dnb Fx execution gateway. SHADOW until all live gates are proven."""
import os
from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from waitress import serve
import mt5_bridge
import mt5_store

if os.getenv('DNB_REQUIRE_DURABLE') != '1' or not mt5_store.remote():
    raise RuntimeError('dnb_requires_durable_database')

app = Flask(__name__)
if os.getenv('FX101_MT5_TRUST_PROXY') == '1':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
app.register_blueprint(mt5_bridge.bp)
app.teardown_appcontext(mt5_store.close_request)

@app.get('/health')
def health():
    try:
        mt5_bridge._ensure_schema()
        mt5_store.db().execute('SELECT 1')
        return jsonify(ok=True, product='dnb Fx', storage='postgres', mode=mt5_bridge.mode(),
                       auto_available=False), 200
    except Exception:
        return jsonify(ok=False, product='dnb Fx', error='storage_unavailable',
                       auto_available=False), 503

if __name__ == '__main__':
    import dnb_source_worker
    dnb_source_worker.start(app)
    proxy = os.getenv('FX101_MT5_TRUST_PROXY') == '1'
    serve(app, host='0.0.0.0', port=int(os.getenv('PORT','10000')), threads=4,
          trusted_proxy='*' if proxy else None,
          trusted_proxy_headers={'x-forwarded-proto'} if proxy else set(),
          max_request_body_size=mt5_bridge.MAX_BYTES)
