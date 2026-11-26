from flask import Blueprint, current_app, request
from flask_login import login_required

from app.models.user import UserRole
from app.responses import error_response, success_response
from app.security.permissions import roles_required
from app.services.errors import OrderError
from app.services.report_service import (
    date_bounds,
    report_categories,
    report_overview,
    report_orders,
    report_peak_hours,
    report_popular_items,
    report_sales,
)

reports_bp = Blueprint("reports", __name__, url_prefix="/api/admin/reports")


def _run_report(fn, key=None, *args):
    """Run a report. List results are wrapped under `key` so every response is an object.

    The date window comes from date_bounds(), the same helper the service documents, so routes
    and service never disagree about where a canteen day starts and ends.
    """
    try:
        start, end = date_bounds(request.args)
        result = fn(start, end, *args)
    except OrderError as exc:
        return error_response(exc.code, exc.message, exc.status)
    data = {key: result} if key else result
    return success_response("Report retrieved", data)


@reports_bp.get("/overview")
@login_required
@roles_required(UserRole.ADMIN)
def overview():
    return _run_report(report_overview)


@reports_bp.get("/sales")
@login_required
@roles_required(UserRole.ADMIN)
def sales():
    return _run_report(report_sales, "days")


@reports_bp.get("/popular-items")
@login_required
@roles_required(UserRole.ADMIN)
def popular_items():
    try:
        limit = int(request.args.get("limit", "10"))
        if not 1 <= limit <= 50:
            raise ValueError
    except (TypeError, ValueError):
        return error_response("INVALID_PAGINATION", "'limit' must be between 1 and 50.", 400)
    return _run_report(report_popular_items, "items", limit)


@reports_bp.get("/categories")
@login_required
@roles_required(UserRole.ADMIN)
def categories():
    return _run_report(report_categories, "categories")


@reports_bp.get("/peak-hours")
@login_required
@roles_required(UserRole.ADMIN)
def peak_hours():
    try:
        start, end = date_bounds(request.args)
        hours = report_peak_hours(start, end)
    except OrderError as exc:
        return error_response(exc.code, exc.message, exc.status)
    return success_response("Report retrieved", {
        "hours": hours,
        "timezone_offset_minutes": int(current_app.config["CANTEEN_UTC_OFFSET_MINUTES"]),
    })


@reports_bp.get("/orders")
@login_required
@roles_required(UserRole.ADMIN)
def orders():
    return _run_report(report_orders)
