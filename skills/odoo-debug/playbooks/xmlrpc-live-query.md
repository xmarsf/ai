# xmlrpc-live-query

Applies when: probing a live/dev/remote Odoo instance for verification (e.g. a bug
report against real data, reachable via `.env` credentials or an API key), instead of
guessing from a UI description or bug-report text alone.

Entry point: [the odoo skill](../../odoo/SKILL.md)
Called by: [diagnosis-before-implementation](../../odoo/playbooks/diagnosis-before-implementation.md), [live-debug](live-debug.md), [missing-required-field-fallback](../../odoo-model/playbooks/missing-required-field-fallback.md)

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] **Prefer XML-RPC (or JSON-RPC) with an API key over browser automation** —
   faster, doesn't require handling a password in a browser form (the safety rules
   prohibit doing that on the user's behalf), and returns structured data directly.
   ```python
   import xmlrpc.client
   common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
   uid = common.authenticate(db, username, api_key, {})  # api_key as password
   models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
   models.execute_kw(db, uid, api_key, 'model.name', 'search_read', [[domain]], {'fields': [...]})
   ```
- [ ] **Keep the `execute_kw` shape exact**: positional args in the args list,
   keyword options in the final kwargs dict. E.g. call `read` as `execute_kw(db, uid,
   key, model, "read", [[ids]], {"fields": [...]})` — putting `fields` positionally
   instead of in the kwargs dict makes Odoo treat it as a field name and report a
   misleading invalid-field error.
- [ ] **If the first username given fails** (`uid == False`), don't assume the API
   key is invalid — ask the user which login the key belongs to (one run: the user's
   own username failed but `admin` worked with the same key).
- [ ] **Keep request intent and returned fields minimal**; never paste account,
   password, token, session cookie, database, or host details into a playbook,
   report, agent prompt, or issue comment — refer to the `.env` path and key names
   instead.
- [ ] **Use browser automation only as a fallback** when RPC cannot observe the bug
   (client-side rendering, asset, tour, or JS-console issues) — capture only
   screenshots, console errors, and failed XHR URLs/statuses; never session cookies
   or headers.

## Relevant knowledge-base

Process only — no Odoo-mechanics content lives here.
