# TrayUP Security Audit

**Audit date:** 2026-11-25  
**Audited revision:** `7cc05b748805f820fb3ff7793bc0e842adaed7fa`  
**Remediation commit:** see the commit that adds this report.

## Scope and method

Reviewed the tracked project tree (150 entries; 145 text/config/source files), including Flask routes/services/models, frontend scripts/pages, deployment files, requirements, Firebase rules, and the source tree of the collection QR feature. Pattern-based secret checks covered current tracked text files and the 53 commits returned by GitHub's first-page `main` history listing. The history check searched commit patches for common provider tokens, JWT-like values, private-key PEM blocks, credential-bearing database URIs, service-account private keys, OAuth client secrets, and similar high-confidence patterns. No secret values are reproduced here.

This is a repository-level audit. The auditor cannot inspect local-only files, private CI variables, Render/Vercel environment values, Firebase IAM/database state, Razorpay dashboard configuration, or GitHub repository-security settings. The history check covers the commits reachable through the returned `main` history page; it does not prove that no credential ever existed in other refs, forks, local clones, logs, or external systems.

## Findings and changes

| Severity | Finding | Change |
| --- | --- | --- |
| High | Admin and kitchen login converted failed backend authentication into local demo roles and then opened privileged dashboards. | Removed those fallbacks. Real admin/kitchen views now require a successful backend login and an exact `ADMIN`/`KITCHEN` role. |
| High | Kitchen scanner could show a demo verification/confirmation after the backend rejected a collection token or confirmation. | Removed simulated verification and completion. The UI reports success only after the server confirms collection. |
| High | Kitchen dashboard converted backend errors into demo orders and allowed simulated order-status changes. | Demo mode now requires an explicit `?demo=1` query and is read-only; normal mode displays an error and never performs local status changes. |
| High | Authenticated order-list, order-detail, tracking and collection-code routes were not all restricted to student accounts; payment creation/verification also lacked explicit student-role checks. | Added server-side `STUDENT` guards and regression tests for staff/admin access. |
| Medium | Admin and kitchen views rendered backend-controlled names, statuses, IDs and timestamps via HTML string interpolation. Admin menu/staff/category views also rendered stored values without escaping. | Added contextual HTML escaping before interpolation in the affected admin/kitchen views. |
| Medium | Firebase Realtime Database project URL was embedded in tracked application/deployment configuration. | Removed it from source defaults and `.env.example`; Render now requires the endpoint to be entered as an unsynced environment value. |
| Medium | Ignore rules did not comprehensively cover cloud credential JSON, private keys, certificates, keystores and infrastructure state files. | Expanded `.gitignore` and retained `.env.example` as the sole environment template exception. |
| Medium | Flask and Werkzeug minimums were too permissive; `pip-audit` also found pytest 8.4.2 and setuptools 80.10.2 vulnerable in the development/build environment. | Raised floors to Flask 3.1.3, Werkzeug 3.1.9, pytest 9.0.3 and setuptools 84.1.0. |
| Medium | Request payload size was not explicitly bounded. | Added a 1 MiB Flask request-body limit. |
| Medium | Security headers did not explicitly disable browser geolocation or set HSTS on HTTPS responses. | Added HSTS on secure requests, Permissions Policy (`geolocation=()`; camera remains available for collection QR scanning), frame/content-type/referrer policies, and `Vary: Cookie`. |
| Low | Webhook processing stored raw exception strings in the webhook audit row. Provider/client exception messages can contain operational details. | Webhook audit errors now store a stable application error code or exception class, not raw exception text. |
| Hardening | Password hashing algorithm was implicit in Werkzeug defaults. | Password creation now explicitly uses scrypt; Werkzeug continues to verify existing supported hash strings. |

## Checks and observations

- `database.rules.json` is deny-by-default: database root `.read` and `.write` are both false. This is preserved.
- Firebase Admin SDK is server-side only. The mirrored order payload deliberately excludes student phone/email, tokens and credentials.
- Vercel uses a same-origin `/api` rewrite to the backend. No permissive wildcard CORS configuration was found in the reviewed app.
- Reviewed route/service SQL paths use SQLAlchemy ORM and a static health-check query; no interpolated SQL execution pattern was found in the reviewed sources.
- No user-controlled file-upload route was found in the reviewed Flask routes. The static frontend is served with Werkzeug `send_from_directory`, which constrains paths to the configured frontend directory.
- No high-confidence provider-token, private-key, service-account private-key or credential-bearing database-URI pattern was confirmed in current tracked files or the inspected commit patches. A public Firebase RTDB project endpoint was present in pre-remediation history; it is not an authentication credential, but it has been removed from the current source tree.
- No tracked `.env`, service-account JSON, PEM/private-key, certificate or keystore file was found in the inspected commit trees. `.env.example` contains placeholders/blank secret values.
- No wildcard CORS, `eval`/dynamic code execution, unsafe pickle/YAML loading, or obvious raw SQL interpolation pattern was found in the reviewed route/service/frontend files.

## Dependencies

The existing requirements used broad lower bounds. Two specific current advisories informed direct minimums:

- Flask CVE-2026-27205 affects Flask versions before 3.1.3: https://nvd.nist.gov/vuln/detail/CVE-2026-27205
- Werkzeug GHSA-g6x2-hccm-hh4m identifies versions before 3.1.9 as affected: https://github.com/pallets/werkzeug/security/advisories/GHSA-g6x2-hccm-hh4m
- pytest PYSEC-2026-1845 / CVE-2025-71176 affects versions through 9.0.2; fixed in 9.0.3: https://osv.dev/vulnerability/PYSEC-2026-1845
- setuptools PYSEC-2026-3447 and GHSA-xmj3-9gf7-h52w affected the resolved 80.10.2 release; `pip-audit` identified 84.1.0 as the available fixed release.

Flask-WTF's 1.3.0 release is available from PyPI: https://pypi.org/project/Flask-WTF/

Added CI checks run `pip-audit` against the resolved requirements, Bandit against `app/`, pytest, and Node syntax checks. Dependency resolution and advisory status can change over time; the CI result must be reviewed after this commit. A lockfile is not yet present, so dependency builds are not fully reproducible.

## Credentials and rotation

- **Firebase service-account private key: rotate immediately.** A service-account credential was supplied during the earlier Firebase integration exchange. Even though this audit did not find a service-account JSON/private key in the repository, treat that key as exposed. Create a replacement key in Google Cloud IAM, upload it to Render as a Secret File at `/etc/secrets/serviceAccountKey.json`, check the admin-only Firebase health endpoint, then disable/delete the old key. Never commit the JSON.
- Razorpay Key ID, Key Secret and Webhook Secret are environment-backed and no matching provider-secret pattern was found in repository history. Rotate them if they were pasted into any public repository, issue, log or other untrusted system; update Render and the Razorpay webhook configuration together, verify a test event, then revoke old values.
- The Render-generated `SECRET_KEY` and database connection string are provisioned outside tracked source. Confirm they are unique/current in Render. Rotate only if they were exposed; changing `SECRET_KEY` invalidates active Flask sessions.
- The Firebase Realtime Database URL is a project endpoint, not a private-key credential. It has been removed from the current `main` tree and must be supplied via Render environment configuration. The endpoint was present in earlier `main` commits; it remains viewable in those historical Git objects because no history rewrite was performed.

## Git history

No high-confidence secret pattern was confirmed in the scanned `main` history. This remediation therefore does not rewrite Git history. No force-push was performed. If a credential is later confirmed in another branch, tag, fork or clone, revoke/rotate it first; prepare a reviewed `git-filter-repo` rewrite and only force-push after explicit approval. Collaborators must coordinate a re-clone/reset after any approved rewrite.

## Optional Git-history cleanup for the old Firebase project URL

**Not executed.** The previous Firebase Realtime Database endpoint is present in earlier commits even though it is absent from current `main`. It is a project identifier/endpoint, not a private key or authentication secret. The following procedure rewrites commit history; use it only after an explicit approval, a maintenance window, and coordination with all collaborators.

1. Freeze pushes/merges and make a verified backup mirror:
   ```bash
   git clone --mirror https://github.com/Mashad-pixel/TrayUP.git TrayUP-backup.git
   git clone --mirror https://github.com/Mashad-pixel/TrayUP.git TrayUP-rewrite.git
   cd TrayUP-rewrite.git
   python -m pip install git-filter-repo
   ```
2. Obtain the old endpoint from a trusted local backup or credential manager and place it in `../private-old-firebase-url.txt` with restrictive permissions (`chmod 600`). Do not put the endpoint in shell history, logs, reports, or Git. Create a replacement file containing that local-only value and a safe marker:
   ```bash
   OLD_FIREBASE_URL="$(cat ../private-old-firebase-url.txt)"  # local-only file; never commit or print its contents
   printf '%s==>FIREBASE_DATABASE_URL_REMOVED\n' "$OLD_FIREBASE_URL" > ../trayup-replacements.txt
   git filter-repo --replace-text ../trayup-replacements.txt
   ```
3. Verify the rewritten refs before pushing:
   ```bash
   git log --all -S "$OLD_FIREBASE_URL" --oneline
   git log --all --oneline --decorate -5
   git show-ref
   ```
   The first command should return no commits. Review all branch and tag refs; coordinate any refs not intended for rewriting.
4. `git-filter-repo` may remove the `origin` remote. Re-add it, fetch the current remote main SHA after the push freeze, and use a lease-protected update:
   ```bash
   git remote add origin https://github.com/Mashad-pixel/TrayUP.git
   git fetch origin --prune
   OLD_MAIN_SHA=$(git ls-remote origin refs/heads/main | awk '{print $1}')
   git push --force-with-lease="refs/heads/main:$OLD_MAIN_SHA" origin refs/heads/main:refs/heads/main
   git push --force --tags origin
   ```
   Repeat lease-protected updates for every other rewritten branch after reviewing its old remote SHA. Temporarily adjust branch protection only if GitHub blocks the approved update, then restore it immediately.
5. Ask every collaborator to discard old clones/branches and freshly clone the rewritten repository. Old clones can reintroduce the removed history if pushed later.

Do not run these commands against the live repository until all maintainers approve the history rewrite. Keep the backup mirror offline and access-controlled.

## Remaining risks and required operational steps

1. Enter `FIREBASE_DATABASE_URL` in Render after this commit. The Render blueprint leaves it `sync: false` to avoid embedding the project endpoint in Git. Firebase is enabled in the blueprint and startup will fail closed if the URL or service-account Secret File is missing.
2. Render still uses `memory://` for rate-limit storage and one Gunicorn worker. This is not shared across processes and resets on restart. Configure Redis before adding workers/instances.
3. Review the GitHub Actions results after the push. The audit environment could inspect and edit GitHub source but could not execute the app or pytest locally; no passing test/dependency scan is claimed until CI completes.
4. Confirm GitHub secret scanning and push protection in repository settings; the available repository connection did not expose the security-settings state.
5. Add a strict Content Security Policy after migrating existing inline scripts/event handlers to external scripts/nonces. A strict CSP was not forced here because it could break existing pages.
6. Complete a Render deployment smoke test: login by role, student registration, student order retrieval, kitchen queue, collection QR verification, Firebase health check, and Razorpay test flow.
7. Confirm Vercel/Render environment values and Firebase database access rules directly in their provider dashboards.

## Verification status

**GitHub Actions verification passed on commit `f498cb08537c159845e8b76d52096a851ab8f136` (run #45574810589):**

- `pytest -q`: **212 passed**
- `pip-audit --strict -r requirements.txt`: **No known vulnerabilities found**
- `bandit -q -r app`: **Passed**
- JavaScript syntax check (`node --check` across `frontend` and `tests/frontend`): **Passed**

Repository secret-pattern scans and source reviews were also completed as described above. Live Render/Firebase/Razorpay/Vercel deployment smoke tests were not run, and GitHub repository security-settings state was not available for inspection. Do not treat this repository-level audit as a guarantee that the deployed system is fully secure; complete the operational checks and remaining-risk items above.
