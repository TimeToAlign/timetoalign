import sys
import os
sys.path.append(os.getcwd())
print("DEBUG: importing tests.loader.score.test_loaders")
try:
    from tests.loader.score import test_loaders
    print("DEBUG: Import successful")
except Exception as e:
    import traceback
    traceback.print_exc()
