import sys
import json
import random
from libgrabsite.dupes import DupesOnDisk

def make_heap_object():
	obj = []
	# Try to run into memory corruption by making objects
	for i in range(random.randint(1, 100000)):
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

def main():
	while True:
		obj = make_heap_object()
		do_work_on_heap(obj)
		print(".", end=" ")
		sys.stdout.flush()

if __name__ == '__main__':
	main()
