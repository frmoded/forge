---
type: action
inputs: [a, b]
description: Adds two 3D vectors and prints the result
---

# Python

```python
def compute(context, a, b):
  result = (numpy.array(a) + numpy.array(b)).tolist()
  context.compute("vec3_print", v=result)
  return result
```
