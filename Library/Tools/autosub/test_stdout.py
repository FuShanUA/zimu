import sys
import os
try:
    print("test")
except Exception as e:
    with open("crash.log", "w") as f:
        f.write(str(e))
    sys.exit(1)
