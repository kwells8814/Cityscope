"""Minimal stdlib test runner so the suite executes without pytest installed.
Provides a tiny `pytest` shim (raises) and discovers test_* functions.
The real suite runs under `pytest` unchanged once installed."""
import sys, types, traceback, importlib, inspect, pathlib, contextlib

# --- pytest shim (only the bits our tests use) ---
shim = types.ModuleType("pytest")
class _Raises:
    def __init__(self, exc): self.exc=exc
    def __enter__(self): return self
    def __exit__(self, et, ev, tb):
        if et is None: raise AssertionError(f"DID NOT RAISE {self.exc}")
        return issubclass(et, self.exc)
shim.raises = lambda exc: _Raises(exc)
class _Mark:
    def skipif(self, cond, reason=""):
        def deco(fn):
            fn.__skip__ = bool(cond)
            return fn
        return deco
shim.mark = _Mark()
shim.fixture = lambda *a, **k: (lambda fn: fn)   # no-op; fixtures only used in skipped db tests
sys.modules["pytest"] = shim

sys.path.insert(0, ".")
import os
os.environ.setdefault("CITYSCOPE_DEMO_MODE", "true")  # tests use mock sources
from cityscope.core.logging_setup import configure_logging
configure_logging("ERROR")

test_files = sorted(pathlib.Path("tests").glob("test_*.py"))
passed=failed=0; failures=[]
for tf in test_files:
    mod_name = "tests."+tf.stem
    mod = importlib.import_module(mod_name)
    # module-level skip: if the module set any HAVE_* flag False, skip the file
    if any(k.startswith("HAVE_") and getattr(mod, k) is False
           for k in dir(mod)):
        continue
    setup = getattr(mod, "setup_function", None)
    for name, fn in inspect.getmembers(mod, inspect.isfunction):
        if not name.startswith("test_"): continue
        if fn.__module__ != mod_name: continue
        if getattr(fn, "__skip__", False):
            continue
        if setup:
            with contextlib.suppress(TypeError): setup()
        try:
            fn(); passed+=1
        except Exception as e:
            failed+=1; failures.append((mod_name, name, traceback.format_exc()))
print(f"\n{'='*50}\n{passed} passed, {failed} failed\n{'='*50}")
for m,n,tb in failures:
    print(f"\nFAIL {m}::{n}\n{tb}")
sys.exit(1 if failed else 0)
