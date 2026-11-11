"""Pengamanan server lokal: hanya Mac ini, dan setiap perubahan wajib membawa token per peluncuran.

Ini mencegah situs lain yang terbuka di browser memakai http://127.0.0.1:PORT (CSRF / DNS rebinding).
"""
from __future__ import annotations

import secrets

from flask import Flask, jsonify, request

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _forbidden():
    return jsonify(error="Forbidden"), 403


def install(app: Flask, port: int) -> None:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{host}" for host in hosts}

    @app.before_request
    def guard():
        if request.host not in hosts:
            return _forbidden()
        if request.method in SAFE_METHODS:
            return None
        origin = request.headers.get("Origin")
        if origin is not None and origin not in origins:
            return _forbidden()
        body = request.get_json(silent=True)
        supplied = (request.headers.get("X-App-Token")
                    or (body.get("token") if isinstance(body, dict) else None)
                    or request.form.get("token") or "")
        if not secrets.compare_digest(str(supplied), app.config["APP_TOKEN"]):
            return _forbidden()
        return None

    @app.after_request
    def harden(response):
        # No other site may show the app in a frame (clickjacking), and Etsy never sees this local address.
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response
