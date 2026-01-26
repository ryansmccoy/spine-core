# {{ adr.number }}. {{ adr.title }}

**Date**: {{ adr.date }}  
**Status**: {{ adr.status }}  
{% if adr.deciders %}**Deciders**: {{ adr.deciders | join(", ") }}{% endif %}

---

## Context

{{ adr.context }}

## Decision

{{ adr.decision }}

## Rationale

{% for reason in adr.rationale %}
- {{ reason }}
{% endfor %}

## Consequences

### Positive

{% for consequence in adr.positive_consequences %}
- {{ consequence }}
{% endfor %}

### Negative

{% for consequence in adr.negative_consequences %}
- {{ consequence }}
{% endfor %}

{% if adr.example_code %}
## Implementation

```python
{{ adr.example_code }}
```
{% endif %}

{% if adr.related_adrs %}
## Related

{% for related in adr.related_adrs %}
- [{{ related.number }}: {{ related.title }}]({{ related.file_path }})
{% endfor %}
{% endif %}

---

*Generated from code annotations on {{ generated_at.strftime('%Y-%m-%d') }}*
