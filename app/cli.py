import json
import os

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models.menu import MenuItem
from app.models.user import User, UserRole
from app.services.order_service import expire_unpaid_orders
from app.services.menu_service import MenuValidationError, create_menu_item, validate_menu_payload
from app.services.session_service import prune_sessions, revoke_user_sessions
from app.security.account_rules import is_valid_email, is_valid_name, normalize_email, password_problem



@click.command("create-user")
@click.option("--name", required=True, help="Full name of the user.")
@click.option("--email", required=True, help="Login email. Stored in lowercase.")
@click.option(
    "--role",
    type=click.Choice([UserRole.ADMIN, UserRole.KITCHEN, UserRole.STUDENT], case_sensitive=False),
    default=UserRole.STUDENT,
    show_default=True,
    help="Account role.",
)
@click.password_option(help="Password (prompted twice).")
@with_appcontext
def create_user_command(name, email, role, password):
    name = name.strip()
    email = normalize_email(email)
    role = role.upper()

    if not is_valid_name(name):
        raise click.BadParameter("Enter a name with 1 to 100 characters.", param_hint="--name")
    if not is_valid_email(email):
        raise click.BadParameter("Enter a valid email address.", param_hint="--email")

    if not name:
        raise click.BadParameter("Name cannot be empty.", param_hint="--name")

    problem = password_problem(password)
    if problem:
        raise click.BadParameter(problem, param_hint="--password")

    if User.query.filter_by(email=email).first():
        raise click.ClickException(f"A user with email {email} already exists.")

    user = User(name=name, email=email, role=role, is_active=True)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    click.echo(f"Created {user.role} user {user.email} (id {user.id}).")


@click.command("expire-orders")
@with_appcontext
def expire_orders_command():
    """Cancel unpaid orders whose payment window has closed, and free their stock.

    Run this on a schedule (for example every minute) so stock is released even when
    no new orders are coming in.
    """
    count = expire_unpaid_orders()
    click.echo(f"Expired {count} unpaid order(s).")


def _user_by_email(email):
    user = User.query.filter_by(email=normalize_email(email)).first()
    if user is None:
        raise click.ClickException("No user has that email address.")
    return user


@click.command("reset-mfa")
@click.option("--email", required=True, help="Account whose authenticator must be re-enrolled.")
@with_appcontext
def reset_mfa_command(email):
    """Remove an account's two-factor setup (for a lost phone) and end its sessions.

    The account must enroll again at its next sign-in.
    """
    user = _user_by_email(email)
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_last_step = None
    user.mfa_failed_attempts = 0
    user.mfa_locked_until = None
    db.session.commit()
    revoked = revoke_user_sessions(user.id)
    click.echo(f"Reset two-factor authentication for {user.email}. Revoked {revoked} session(s).")


@click.command("revoke-sessions")
@click.option("--email", required=True, help="Account whose live sessions should end immediately.")
@with_appcontext
def revoke_sessions_command(email):
    user = _user_by_email(email)
    revoked = revoke_user_sessions(user.id)
    click.echo(f"Revoked {revoked} session(s) for {user.email}.")


@click.command("prune-sessions")
@with_appcontext
def prune_sessions_command():
    """Delete expired and revoked session rows. Run this on a schedule."""
    removed = prune_sessions()
    click.echo(f"Removed {removed} finished session(s).")


SEED_MENU_PATH = os.path.join(os.path.dirname(__file__), "data", "menu_seed.json")


@click.command("seed-menu")
@with_appcontext
def seed_menu_command():
    """Load the starter menu into an empty database. Does nothing if any menu item exists.

    Every entry goes through the same validation as the admin API, and all entries are
    checked before any are written.
    """
    if MenuItem.query.first() is not None:
        click.echo("The menu already has items. Nothing was loaded.")
        return

    with open(SEED_MENU_PATH, encoding="utf-8") as handle:
        entries = json.load(handle)

    for index, entry in enumerate(entries, start=1):
        try:
            validate_menu_payload(entry)
        except MenuValidationError as exc:
            raise click.ClickException(
                f"Seed entry {index} ({entry.get('name')!r}) is invalid: {exc.errors}"
            )

    for entry in entries:
        create_menu_item(entry)
    click.echo(f"Loaded {len(entries)} menu items.")


def register_cli(app):
    app.cli.add_command(seed_menu_command)
    app.cli.add_command(create_user_command)
    app.cli.add_command(expire_orders_command)
    app.cli.add_command(reset_mfa_command)
    app.cli.add_command(revoke_sessions_command)
    app.cli.add_command(prune_sessions_command)
