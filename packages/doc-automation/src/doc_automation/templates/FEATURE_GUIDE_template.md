# {{ feature.title }}

> {{ feature.tagline }}

---

## 🎯 What Is This?

{{ feature.overview }}

## 🏛️ Core Concepts

{% for concept in feature.concepts %}
### {{ concept.title }}

{{ concept.explanation }}

{% if concept.diagram %}
```
{{ concept.diagram }}
```
{% endif %}

{% if concept.examples %}
**Examples:**

{% for example in concept.examples %}
```{{ example.language }}
{{ example.code }}
```

{{ example.description }}

{% endfor %}
{% endif %}

{% endfor %}

## 📚 How It Works

{{ feature.how_it_works }}

## 🚀 Quick Start

```python
{{ feature.quick_start_code }}
```

{% if feature.advanced_topics %}
## 🔍 Advanced Usage

{% for advanced_topic in feature.advanced_topics %}
### {{ advanced_topic.title }}

{{ advanced_topic.content }}
{% endfor %}
{% endif %}

{% if feature.guardrails %}
## ⚠️ Common Pitfalls

{% for pitfall in feature.guardrails %}
- **{{ pitfall.anti_pattern }}**: {{ pitfall.why_bad }}
  - ✅ Instead: {{ pitfall.correct_approach }}
{% endfor %}
{% endif %}

{% if feature.related_docs %}
## 🔗 Related

{% for related in feature.related_docs %}
- [{{ related.title }}]({{ related.path }})
{% endfor %}
{% endif %}

---

*Auto-generated from `{{ feature.source_file }}` on {{ generated_at.strftime('%Y-%m-%d') }}*
