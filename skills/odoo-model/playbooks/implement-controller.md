# Implement a controller (HTTP/JSON/portal route)

Applies when: a task adds or changes an `@http.route` endpoint — a JSON-RPC/API route,
a portal page, or a webhook receiver — that is not just overriding an existing report's
render context.

Entry point: [SKILL.md](../SKILL.md)

## Usage
- used: 0 (tracking started 2026-07-16)
- last used: n/a

## Steps

- [ ] Pick `type` (`http` for a page/redirect/file response, `json` for an RPC-style
  payload) and `auth` (`user`, `public`, or `none`) to match the actual caller — a
  browser form post, an authenticated portal user, or an external webhook.
- [ ] Grep existing `@http.route` declarations across installed addons for path/prefix
  overlap before picking a route path.
- [ ] `csrf=True` stays on for browser-form POSTs under `auth='user'`/`'public'`.
  Disable it only for a verified external caller (webhook), and if disabled, add a
  replacement check (signature/secret/IP allowlist) in the method body — CSRF-off with
  no replacement check is an open endpoint, not a convenience.
- [ ] Inside the method, `request.env` runs as the calling user for `auth='user'`, but
  as the public user for `auth='public'`/`'none'` — an internal record fetch there needs
  an explicit `sudo()` plus a manual ownership/scope check, not just the model's normal
  ACLs. Missing this reads at first like a model access-control bug, not a controller
  one — check the controller's `auth`/`sudo()` combination before chasing the model.
  New model access needed at all → run playbook:
  [implement-security-rule](implement-security-rule.md).
- [ ] Overriding an existing controller method that renders a QWeb template → run
  playbook: [controller-qweb-overrides](controller-qweb-overrides.md).
- [ ] `type='json'` return values are auto-serialized — don't hand-wrap them in a
  `Response` unless a custom status code or header is actually required.
- [ ] Any string returned to a browser template (not raw API JSON) → run playbook:
  the **odoo-wlc** skill (translation round-trip).
- [ ] Verify by calling the route as the caller it's meant for — an anonymous/portal
  session for `auth='public'`, not just the internal/admin session used for the rest
  of the task — since that's exactly the gap the `sudo()`/scope-check step above
  guards against.

## Pitfalls

- Missing `sudo()` (or an unscoped one) on a `public`/portal route surfaces as an
  access error that looks like a model ACL problem; the real cause is the controller's
  auth level not matching what the method body assumes.
- Turning off `csrf` to "make the POST work" without adding a replacement check leaves
  the endpoint open to forgery from any origin.

## Example instance

- (seed entry — fill in with the first run that adds a controller through this
  playbook: route path, `auth`/`type` chosen, and how the sudo/scope check was done.)

## Relevant knowledge-base

- No dedicated vault note yet for controller `auth`/`sudo()` scoping — verify against
  `odoo.http.Controller`/`route` source before relying on this playbook alone, and
  write back a note after the first orchestrated run.
