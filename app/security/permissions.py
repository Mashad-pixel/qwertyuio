from functools import wraps

from flask_login import current_user

from app.responses import error_response


def roles_required(*allowed_roles):
    """Allow the request only if the logged-in user has one of the given roles.

    Always place @login_required above this decorator, so anonymous users
    get a 401 before this check runs.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if current_user.role not in allowed_roles:
                return error_response(
                    "FORBIDDEN",
                    "You do not have permission to do this.",
                    403,
                )
            return view_func(*args, **kwargs)

        return wrapper

    return decorator
