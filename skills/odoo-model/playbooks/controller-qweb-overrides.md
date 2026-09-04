# Controller QWeb rendering overrides

Applies when: overriding a controller method that renders a QWeb template.

Called by: [implement-report](../../odoo-view/playbooks/implement-report.md), [implement-controller](implement-controller.md)

## Usage
- used: 0
- last used: 2026-07-10

## Steps
- [ ] Call `super()` to get the parent response
- [ ] Mutate `response.qcontext` (the template context dict) to add/modify variables
- [ ] Do NOT rebuild the render context inline from scratch — the parent's response includes initialization, post-processing, and framework integration that custom rebuilds miss

## Pitfalls
- Rebuilding the context: missing framework setup, context filters, response headers, streaming pipeline
- Direct context manipulation without super: parent initialization is skipped

## Example instance
```python
def _custom_view(self):
    response = super()._custom_view()  # Get parent's rendered response
    response.qcontext['extra_data'] = self.env[...].search(...)  # Add to context
    return response
```

NOT:
```python
def _custom_view(self):
    context = {...}  # Wrong: rebuilds from scratch, loses parent setup
    return request.render('module.template', context)
```

## Relevant knowledge-base

- note: Controller — `qcontext` override pattern via `super()`.
