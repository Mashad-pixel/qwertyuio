from flask import jsonify


def success_response(message, data=None, status=200):
    return (
        jsonify({
            "success": True,
            "message": message,
            "data": data if data is not None else {},
        }),
        status,
    )


def error_response(code, message, status):
    return (
        jsonify({
            "success": False,
            "message": message,
            "error": {"code": code},
        }),
        status,
    )
