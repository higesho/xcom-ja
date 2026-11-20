import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from le import LE
e = LE()
print(e.dis(int(sys.argv[1], 16), int(sys.argv[2]) if len(sys.argv) > 2 else 60))
