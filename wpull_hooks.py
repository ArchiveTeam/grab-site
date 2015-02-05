import re
import os
import json
from urllib.request import urlopen
from ignoracle import Ignoracle, parameterize_record_info

def getPatternsForIgnoreSet(name):
	assert name != "", name
	print("Fetching ArchiveBot/master/db/ignore_patterns/%s.json" % name)
	return json.loads(urlopen("https://raw.githubusercontent.com/ArchiveTeam/ArchiveBot/master/db/ignore_patterns/%s.json" % name).read().decode("utf-8"))["patterns"]

ignore_sets = set(os.environ.get('IGNORE_SETS', '').strip().split(','))
ignore_sets.add('global')

ignoracle = Ignoracle()
ignores = set()
for igset in ignore_sets:
	ignores.update(getPatternsForIgnoreSet(igset))


def ignore_url_p(url, record_info):
	'''
	Returns whether a URL should be ignored.
	'''
	parameters = parameterize_record_info(record_info)
	return ignoracle.ignores(url, **parameters)


def accept_url(url_info, record_info, verdict, reasons):
	url = url_info['url']

	if url.startswith('data:'):
		# data: URLs aren't something you can grab, so drop them to avoid ignore
		# checking and ignore logging.
		return False

	pattern = ignore_url_p(url, record_info)
	if pattern:
		print("IGNOR %s by %s" % (url, pattern))
		return False

	# If we get here, none of our ignores apply.	Return the original verdict.
	return verdict


# Regular expressions for server headers go here
ICY_FIELD_PATTERN = re.compile('Icy-|Ice-|X-Audiocast-')
ICY_VALUE_PATTERN = re.compile('icecast', re.IGNORECASE)

def handle_pre_response(url_info, url_record, response_info):
	url = url_info['url']

	# Check if server version starts with ICY
	if response_info.get('version', '') == 'ICY':
		maybe_log_ignore(url, '[icy version]')

		return wpull_hook.actions.FINISH

	# Loop through all the server headers for matches
	for field, value in response_info.get('fields', []):
		if ICY_FIELD_PATTERN.match(field):
			maybe_log_ignore(url, '[icy field]')

			return wpull_hook.actions.FINISH

		if field == 'Server' and ICY_VALUE_PATTERN.match(value):
			maybe_log_ignore(url, '[icy server]')

			return wpull_hook.actions.FINISH

	# Nothing matched, allow download
	return wpull_hook.actions.NORMAL


assert 2 in wpull_hook.callbacks.AVAILABLE_VERSIONS

wpull_hook.callbacks.version = 2
wpull_hook.callbacks.accept_url = accept_url
wpull_hook.callbacks.handle_pre_response = handle_pre_response
