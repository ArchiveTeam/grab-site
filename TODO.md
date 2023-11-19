# TODO

## html5lib>=1

- [x] [_tokenizer](https://github.com/html5lib/html5lib-python/pull/270)

```python
import sys
sys.modules["html5lib.tokenizer"] = __import__("html5lib._tokenizer")
```

## python>=3.7

- [x] [async def](https://github.com/python/cpython/issues/74591)

```patch
diff --git a/.venv/lib/python3.7/site-packages/wpull/driver/process.py b/.venv/lib/python3.7/site-packages/wpull/driver/process.py
index e370538..48d1d39 100644
--- a/.venv/lib/python3.7/site-packages/wpull/driver/process.py
+++ b/.venv/lib/python3.7/site-packages/wpull/driver/process.py
@@ -53,8 +53,8 @@ class Process(object):
         )
         self._process = yield from process_future

-        self._stderr_reader = asyncio.async(self._read_stderr())
-        self._stdout_reader = asyncio.async(self._read_stdout())
+        self._stderr_reader = asyncio.ensure_future(self._read_stderr())
+        self._stdout_reader = asyncio.ensure_future(self._read_stdout())

         if use_atexit:
             atexit.register(self.close)
```

## python>=3.10

- [x] [collections.abc](https://github.com/python/cpython/issues/81505)

```python
import collections
from collections.abc import Hashable, Mapping, MutableMapping
from typing import Callable
collections.Callable = Callable
collections.Hashable = Hashable
collections.Mapping = Mapping
collections.MutableMapping = MutableMapping
```

## python>=3.11

- [x] [@asyncio.coroutine](https://github.com/python/cpython/issues/87382)

```python
import asyncio
# https://github.com/python/cpython/blob/68b34a720485f399e8699235b8f4e08f227dd43b/Lib/asyncio/coroutines.py#L105
def coroutine(): ...
_is_coroutine = object()
asyncio.coroutine = coroutine
```

## tornado>=5

- [x] [SSL](https://github.com/tornadoweb/tornado/pull/2177)

```python
from ssl import CertificateError
from tornado import netutil
netutil.SSLCertificateError = CertificateError
```
