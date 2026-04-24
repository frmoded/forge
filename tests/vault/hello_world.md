---
type: action
inputs: []
description: Hello world 
---

# English

[[greet]] "world"

---

# Python

```python
def run(context):
  return context.execute("greet", name="world")
```
