"""
This is a sample script that can be passed to grab-site --custom-hooks=. It
1) drops http:// URLs before they can be queued
2) aborts responses that have a Content-Type: that starts with 'audio/'
3) queues additional URLs on Twitter to get original-quality images

For self-help on writing hooks, `git clone https://github.com/chfoo/wpull`,
`git checkout v1.2.3`, and read wpull/hook.py.
"""

import re

accept_url_grabsite = wpull_hook.callbacks.accept_url
def accept_url(url_info, record_info, verdict, reasons):
	url = url_info['url']
	if url.startswith("http://"):
		print("Dropping insecure URL %s" % url)
		return False
	return accept_url_grabsite(url_info, record_info, verdict, reasons)

def has_content_type_audio(response_info):
	try:
		t = list(p for p in response_info["fields"] if p[0] == "Content-Type")[0][1]
		return t.lower().startswith("audio/")
	except (IndexError, ValueError):
		return False

handle_pre_response_grabsite = wpull_hook.callbacks.handle_pre_response
def handle_pre_response(url_info, url_record, response_info):
	url = url_info['url']
	if has_content_type_audio(response_info):
		print("Dropping %s because it has audio mime type" % url)
		return wpull_hook.actions.FINISH
	return handle_pre_response_grabsite(url_info, url_record, response_info)

def get_urls(filename, url_info, document_info):
	url = url_info["url"]
	# If we see this URL, also queue the URL for the :orig quality image
	if url.startswith("https://pbs.twimg.com/media/"):
		new_url = re.sub(":[a-z]{1,10}$", "", url) + ":orig"
		# see wpull/item.py:LinkType
		extra_urls = [dict(url=new_url, link_type="media", inline=True)]
		print("Queueing %r" % (extra_urls,))
		return extra_urls

wpull_hook.callbacks.accept_url = accept_url
wpull_hook.callbacks.handle_pre_response = handle_pre_response
wpull_hook.callbacks.get_urls = get_urls
