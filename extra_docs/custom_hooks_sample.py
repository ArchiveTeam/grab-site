"""
This is a sample script that can be passed to grab-site --custom-hooks=.
It drops http:// URLs before they can be queued, and it aborts responses
that have a Content-Type: that starts with 'audio/'
"""

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

wpull_hook.callbacks.accept_url = accept_url
wpull_hook.callbacks.handle_pre_response = handle_pre_response
