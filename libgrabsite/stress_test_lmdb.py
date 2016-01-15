import os
import sys
import json
import hashlib
import random
import tempfile
from libgrabsite.dupes import DupesOnDisk

def make_heap_object():
	obj = []
	# Try to run into memory corruption by making objects
	for i in range(random.randint(1, 1000000)):
		obj.append([{"a": str(i)}])
	return obj

def do_work_on_heap(obj):
	expect = 0
	for x in obj:
		num = int(x[0]["a"])
		assert num == expect, (num, expect)
		expect += 1
	copy = json.loads(json.dumps(obj))
	expect = 0
	for x in copy:
		num = int(x[0]["a"])
		assert num == expect, (num, expect)
		expect += 1

d = DupesOnDisk(tempfile.NamedTemporaryFile(prefix='stresstest').name)

def get_random_digest():
	# TODO: optimize?
	rand = os.urandom(16)
	return hashlib.md5(rand).digest()

def get_fake_url():
	if random.random() < 0.1:
		fake_url = " " * random.randint(1, 1000)
	else:
		fake_url = " " * random.randint(1, 100)
	return fake_url

def do_possibly_corrupting_work():
	for i in range(random.randint(1, 100000)):
		d.get_old_url(get_random_digest())
		key = get_random_digest()
		url = get_fake_url()
		d.set_old_url(key, url)
		assert d.get_old_url(key) == url

def main():
	while True:
		obj = make_heap_object()
		do_possibly_corrupting_work()
		do_work_on_heap(obj)
		print(".", end=" ")
		sys.stdout.flush()

if __name__ == '__main__':
	main()
