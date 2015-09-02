"""
Duplicate page content database.
"""

class DupesOnDisk(object):
	def __init__(self, filename):
		import lmdb
		last_error = None
		# Try 1TB, 2GB, 1GB, 512MB, 256MB, 128MB, then give up.
		# "Must be <2GB on 32-bit" https://lmdb.readthedocs.org/en/release/
		# but sometimes needs to be even lower.
		for map_size in (1024**4, 2**31 - 1, 2**30 - 1, 2**29 - 1, 2**28 - 1, 2**27 - 1):
			try:
				self._env = lmdb.open(
					filename,
					# Can't use writemap=True on OS X because it does not fully support sparse files
					# https://acid.readthedocs.org/en/latest/engines.html
					# Don't use writemap=True elsewhere because enormous sparse files get copied
					# and make a non-sparse mess
					writemap=False,
					sync=False,
					metasync=False,
					# http://lmdb.readthedocs.org/en/release/#lmdb.Environment
					map_size=map_size)
			except (OverflowError, lmdb.MemoryError) as e:
				last_error = e
			else:
				print("Created lmdb db with map_size=%d" % (map_size,))
				last_error = None
				break
		if last_error is not None:
			raise last_error

	def get_old_url(self, digest):
		with self._env.begin() as txn:
			maybe_url = txn.get(digest)
			if maybe_url is None:
				return maybe_url
			return maybe_url.decode('utf-8')

	def set_old_url(self, digest, url):
		with self._env.begin(write=True) as txn:
			return txn.put(digest, url.encode("utf-8"))


class DupesInMemory(object):
	def __init__(self):
		self._digests = {}

	def get_old_url(self, digest):
		return self._digests.get(digest)

	def set_old_url(self, digest, url):
		self._digests[digest] = url


__all__ = [
	'DupesOnDisk', 'DupesInMemory'
]
