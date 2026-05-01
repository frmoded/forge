---
type: action
inputs: [v]
description: Prints a 3D vector
---

# Python

```python
def compute(context, v):
  arr = numpy.array(v)
  print(f"({arr[0]}, {arr[1]}, {arr[2]})")
  return arr.tolist()
```
