---
type: action
inputs: [a, b]
description: Adds two 3D vectors and prints the result
---

# Python

```python
def vec3_add(context, a, b):
  result = (numpy.array(a) + numpy.array(b)).tolist()
  context.execute("vec3_print", v=result)
  return result
```
