from flask import Flask, jsonify, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from app.responses import error_response
from app.cli import register_cli
from app.config import DEV_SECRET_KEY, config_map
from app.extensions import csrf, db, limiter, login_manager, migrate
from app.models.user import User, UserRole
from app.routes.admin import admin_bp
from app.routes.account import account_bp
from app.routes.admin_orders import admin_orders_bp
from app.routes.admin_staff import admin_staff_bp
from app.routes.admin_refunds import admin_refunds_bp
from app.routes.auth import auth_bp
from app.routes.frontend import frontend_bp
from app.routes.kitchen import kitchen_bp
from app.routes.orders import orders_bp
from app.routes.payments import payments_bp
from app.routes.public import public_bp
from app.routes.recovery import recovery_bp
from app.routes.reports import reports_bp
from app.security.csp import build_api_policy, build_frontend_policy
from app.security.production_checks import production_problems
from app.services.firebase_service import initialize_firebase
from app.services.session_service import current_session_mfa_verified, validate_session_for

# Endpoints an administrator can reach before completing two-factor sign-in: signing in or
# out, checking who they are, and enrolling a second factor.
MFA_EXEMPT_ENDPOINTS = frozenset({
    "auth.login",
    "auth.register",
    "auth.logout",
    "auth.me",
    "auth.mfa_setup",
    "auth.mfa_confirm",
})
# Public pages and the health/menu/CSRF endpoints never need an administrator session.
MFA_UNGATED_BLUEPRINTS = frozenset({"frontend", "public"})


@login_manager.user_loader
def load_user(user_id):
    try:
        user = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

    if user is None or not user.is_active:
        return None
    # The signed cookie only names the user. The server must still have a live session row.
    if validate_session_for(user) is None:
        return None
    return user


@login_manager.unauthorized_handler
def unauthorized():
    return (
        jsonify({
            "success": False,
            "message": "Please log in first.",
            "error": {"code": "AUTH_REQUIRED"},
        }),
        401,
    )


def create_app(config_name="production"):
    if config_name not in config_map:
        raise ValueError(f"Unknown config '{config_name}'. Use: {', '.join(config_map)}.")

    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    if config_name == "production":
        problems = production_problems(app.config, DEV_SECRET_KEY)
        if problems:
            raise RuntimeError(
                "Refusing to start with an unsafe production configuration:\n- " + "\n- ".join(problems)
            )

    frontend_policy = build_frontend_policy(
        app.config["MENU_IMAGE_ALLOWED_HOSTS"],
        upgrade_insecure=app.config.get("CSP_UPGRADE_INSECURE", False),
    )
    api_policy = build_api_policy()
    csp_header = (
        "Content-Security-Policy-Report-Only"
        if app.config.get("CSP_REPORT_ONLY", False)
        else "Content-Security-Policy"
    )

    trusted_proxy_count = app.config.get("TRUSTED_PROXY_COUNT", 0)
    if trusted_proxy_count:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=trusted_proxy_count,
            x_proto=trusted_proxy_count,
        )

    db.init_app(app)
    initialize_firebase(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    @app.errorhandler(429)
    def handle_rate_limited(exc):
        return error_response(
            "RATE_LIMITED",
            "Too many attempts. Wait a few minutes and try again.",
            429,
        )

    @app.errorhandler(CSRFError)
    def handle_csrf_error(exc):
        return error_response(
            "CSRF_TOKEN_INVALID",
            "The CSRF token is missing or invalid. Refresh the token and retry.",
            400,
        )

    @app.before_request
    def require_admin_mfa():
        endpoint = request.endpoint
        if endpoint is None or endpoint.split(".", 1)[0] in MFA_UNGATED_BLUEPRINTS:
            return None
        if endpoint in MFA_EXEMPT_ENDPOINTS or not current_user.is_authenticated:
            return None
        if current_user.role == UserRole.ADMIN and not current_session_mfa_verified():
            return error_response(
                "MFA_REQUIRED",
                "Two-factor authentication is required for administrator access.",
                403,
            )
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault(
            csp_header,
            frontend_policy if response.mimetype == "text/html" else api_policy,
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(self)")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        response.vary.add("Cookie")
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    limiter.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(frontend_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(admin_orders_bp)
    app.register_blueprint(kitchen_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(admin_refunds_bp)
    app.register_blueprint(admin_staff_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(recovery_bp)

    register_cli(app)
    return app
