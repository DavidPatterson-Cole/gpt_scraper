#!/usr/bin/env python3
#
# natbot.py
#
# Set OPENAI_API_KEY to your API key, and then run this from a terminal.
#

from playwright.sync_api import sync_playwright
import time
from sys import argv, exit, platform
import openai
import os
# import asyncio
# from playwright.async_api import async_playwright
# import subprocess
# from chatgpt_wrapper import ChatGPT
# import argparse
# import base64
# import cmd
# import json
# import operator
# import platform
# import sys
import uuid
# from functools import reduce
from time import sleep

quiet = False
if len(argv) >= 2:
	if argv[1] == '-q' or argv[1] == '--quiet':
		quiet = True
		print(
			"Running in quiet mode (HTML and other content hidden); \n"
			+ "exercise caution when running suggested commands."
		)

prompt_template = """
You are an agent controlling a browser. You are given:
	(1) an objective that you are trying to achieve
	(2) the URL of your current web page
	(3) a simplified text description of what's visible in the browser window (more on that below)
You can issue these commands:
	SCROLL UP - scroll up one page
	SCROLL DOWN - scroll down one page
	CLICK X - click on a given element. You can only click on links, buttons, and inputs!
	TYPE X "TEXT" - type the specified text into the input with id X
	TYPESUBMIT X "TEXT" - same as TYPE above, except then it presses ENTER to submit the form
  ANSWER "TEXT" - print out the specified text which answers the objective
The format of the browser content is highly simplified; all formatting elements are stripped.
Interactive elements such as links, inputs, buttons are represented like this:
		<link id=1>text</link>
		<button id=2>text</button>
		<input id=3>text</input>
Images are rendered as their alt text like this:
		<img id=4 alt=""/>
Based on your given objective, issue whatever command you believe will get you closest to achieving your goal.
You always start on Google; you should submit a search query to Google that will take you to the best page for
achieving your objective. And then interact with that page to achieve your objective.
If you find yourself on Google and there are no search results displayed yet, you should probably issue a command 
like "TYPESUBMIT 7 "search query"" to get to a more useful page.
Then, if you find yourself on a Google search results page, you might issue the command "CLICK 24" to click
on the first link in the search results. (If your previous command was a TYPESUBMIT your next command should
probably be a CLICK.)
Don't try to interact with elements that you can't see.
Here are some examples:
EXAMPLE 1:
==================================================
CURRENT BROWSER CONTENT:
------------------
<link id=1>About</link>
<link id=2>Store</link>
<link id=3>Gmail</link>
<link id=4>Images</link>
<link id=5>(Google apps)</link>
<link id=6>Sign in</link>
<img id=7 alt="(Google)"/>
<input id=8 alt="Search"></input>
<button id=9>(Search by voice)</button>
<button id=10>(Google Search)</button>
<button id=11>(I'm Feeling Lucky)</button>
<link id=12>Advertising</link>
<link id=13>Business</link>
<link id=14>How Search works</link>
<link id=15>Carbon neutral since 2007</link>
<link id=16>Privacy</link>
<link id=17>Terms</link>
<text id=18>Settings</text>
------------------
OBJECTIVE: Find a 2 bedroom house for sale in Anchorage AK for under $750k
CURRENT URL: https://www.google.com/
YOUR COMMAND: 
TYPESUBMIT 8 "anchorage redfin"
==================================================
EXAMPLE 2:
==================================================
CURRENT BROWSER CONTENT:
------------------
<link id=1>About</link>
<link id=2>Store</link>
<link id=3>Gmail</link>
<link id=4>Images</link>
<link id=5>(Google apps)</link>
<link id=6>Sign in</link>
<img id=7 alt="(Google)"/>
<input id=8 alt="Search"></input>
<button id=9>(Search by voice)</button>
<button id=10>(Google Search)</button>
<button id=11>(I'm Feeling Lucky)</button>
<link id=12>Advertising</link>
<link id=13>Business</link>
<link id=14>How Search works</link>
<link id=15>Carbon neutral since 2007</link>
<link id=16>Privacy</link>
<link id=17>Terms</link>
<text id=18>Settings</text>
------------------
OBJECTIVE: Make a reservation for 4 at Dorsia at 8pm
CURRENT URL: https://www.google.com/
YOUR COMMAND: 
TYPESUBMIT 8 "dorsia nyc opentable"
==================================================
EXAMPLE 3:
==================================================
CURRENT BROWSER CONTENT:
------------------
<button id=1>For Businesses</button>
<button id=2>Mobile</button>
<button id=3>Help</button>
<button id=4 alt="Language Picker">EN</button>
<link id=5>OpenTable logo</link>
<button id=6 alt ="search">Search</button>
<text id=7>Find your table for any occasion</text>
<button id=8>(Date selector)</button>
<text id=9>Sep 28, 2022</text>
<text id=10>7:00 PM</text>
<text id=11>2 people</text>
<input id=12 alt="Location, Restaurant, or Cuisine"></input> 
<button id=13>Let’s go</button>
<text id=14>It looks like you're in Peninsula. Not correct?</text> 
<button id=15>Get current location</button>
<button id=16>Next</button>
------------------
OBJECTIVE: Make a reservation for 4 for dinner at Dorsia in New York City at 8pm
CURRENT URL: https://www.opentable.com/
YOUR COMMAND: 
TYPESUBMIT 12 "dorsia new york city"
==================================================
The current browser content, objective, and current URL follow. Reply with your next command to the browser.
CURRENT BROWSER CONTENT:
------------------
$browser_content
------------------
OBJECTIVE: $objective
CURRENT URL: $url
PREVIOUS COMMAND: $previous_command
YOUR COMMAND:
"""

black_listed_elements = set(["html", "head", "title", "meta", "iframe", "body", "script", "style", "path", "svg", "br", "::marker",])

class Crawler:

	session_div_id = "chatgpt-wrapper-session-data"

	def __init__(self):
		self.browser = (
      # async_playwright()
      # .start()
			# .chromium.launch(headless=False)
			# self.context = self.browser.new_context()
			# self.page = self.context.new_page()

			# Attempted to swith to Firefox but it doesn't work because of the CDP thing
			sync_playwright()
			.start()
			.firefox.launch_persistent_context(
        user_data_dir="/tmp/playwright",
				headless=True,
			)
		)
		self.session = None
		self.parent_message_id = str(uuid.uuid4())
		self.conversation_id = None
		self.page = self.browser.new_page()
		self.page.set_viewport_size({"width": 1280, "height": 1080})
  
	# Added this 
	def new_tab(self):
		# self.page2 = self.browser.play.launch_persistent_context(
    #         user_data_dir="/tmp/playwright",
    #         headless=headless,
    #     )
		self.page2 = self.browser.new_page()
		self.page2.goto("https://chat.openai.com/")

	def refresh_session(self):
			self.page2.evaluate(
				"""
				const xhr = new XMLHttpRequest();
				xhr.open('GET', 'https://chat.openai.com/api/auth/session');
				xhr.onload = () => {
					if(xhr.status == 200) {
						var mydiv = document.createElement('DIV');
						mydiv.id = "SESSION_DIV_ID"
						mydiv.innerHTML = xhr.responseText;
						document.body.appendChild(mydiv);
					}
				};
				xhr.send();
				""".replace(
					"SESSION_DIV_ID", self.session_div_id
				)
			)

			while True:
				print('session div:', self.session_div_id)
				session_datas = self.page2.query_selector_all(f"div#{self.session_div_id}")
				if len(session_datas) > 0:
					break
				sleep(0.2)

			session_data = json.loads(session_datas[0].inner_text())
			self.session = session_data

			self.page2.evaluate(f"document.getElementById('{self.session_div_id}').remove()")

	def _cleanup_divs(self):
		self.page2.evaluate(f"document.getElementById('{self.stream_div_id}').remove()")
		self.page2.evaluate(f"document.getElementById('{self.eof_div_id}').remove()")

	def ask_stream(self, prompt: str):
		if self.session is None:
			self.refresh_session()
		print('made it here')
		new_message_id = str(uuid.uuid4())
		if "accessToken" not in self.session:
			yield (
				"Your ChatGPT session is not usable.\n"
				"* Run this program with the `install` parameter and log in to ChatGPT.\n"
				"* If you think you are already logged in, try running the `session` command."
			)
			return

		request = {
			"messages": [
				{
					"id": new_message_id,
					"role": "user",
					"content": {"content_type": "text", "parts": [prompt]},
				}
			],
			"model": "text-davinci-002-render",
			"conversation_id": self.conversation_id,
			"parent_message_id": self.parent_message_id,
			"action": "next",
		}

		code = (
			"""
			const stream_div = document.createElement('DIV');
			stream_div.id = "STREAM_DIV_ID";
			document.body.appendChild(stream_div);
			const xhr = new XMLHttpRequest();
			xhr.open('POST', 'https://chat.openai.com/backend-api/conversation');
			xhr.setRequestHeader('Accept', 'text/event-stream');
			xhr.setRequestHeader('Content-Type', 'application/json');
			xhr.setRequestHeader('Authorization', 'Bearer BEARER_TOKEN');
			xhr.responseType = 'stream';
			xhr.onreadystatechange = function() {
				var newEvent;
				if(xhr.readyState == 3 || xhr.readyState == 4) {
					const newData = xhr.response.substr(xhr.seenBytes);
					try {
						const newEvents = newData.split(/\\n\\n/).reverse();
						newEvents.shift();
						if(newEvents[0] == "data: [DONE]") {
							newEvents.shift();
						}
						if(newEvents.length > 0) {
							newEvent = newEvents[0].substring(6);
							// using XHR for eventstream sucks and occasionally ive seen incomplete
							// json objects come through  JSON.parse will throw if that happens, and
							// that should just skip until we get a full response.
							JSON.parse(newEvent);
						}
					} catch (err) {
						console.log(err);
						return;
					}
					if(newEvent !== undefined) {
						stream_div.innerHTML = btoa(newEvent);
						xhr.seenBytes = xhr.responseText.length;
					}
				}
				if(xhr.readyState == 4) {
					const eof_div = document.createElement('DIV');
					eof_div.id = "EOF_DIV_ID";
					document.body.appendChild(eof_div);
				}
			};
			xhr.send(JSON.stringify(REQUEST_JSON));
			""".replace(
				"BEARER_TOKEN", self.session["accessToken"]
			)
			.replace("REQUEST_JSON", json.dumps(request))
			.replace("STREAM_DIV_ID", self.stream_div_id)
			.replace("EOF_DIV_ID", self.eof_div_id)
		)

		self.page2.evaluate(code)

		last_event_msg = ""
		while True:
			eof_datas = self.page2.query_selector_all(f"div#{self.eof_div_id}")
			conversation_datas = self.page2.query_selector_all(
				f"div#{self.stream_div_id}"
			)
			if len(conversation_datas) == 0:
				continue
			
			full_event_message = None
			
			try:
				event_raw = base64.b64decode(conversation_datas[0].inner_html())
				if len(event_raw) > 0:
					event = json.loads(event_raw)
					if event is not None:
						self.parent_message_id = event["message"]["id"]
						self.conversation_id = event["conversation_id"]
						full_event_message = "\n".join(
							event["message"]["content"]["parts"]
						)
			except Exception:
				yield (
					"Failed to read response from ChatGPT.  Tips:\n"
					" * Try again.  ChatGPT can be flaky.\n"
					" * Use the `session` command to refresh your session, and then try again.\n"
					" * Restart the program in the `install` mode and make sure you are logged in."
				)
				break

			if full_event_message is not None:
				chunk = full_event_message[len(last_event_msg) :]
				last_event_msg = full_event_message
				yield chunk

			# if we saw the eof signal, this was the last event we
			# # should process and we are done
			if len(eof_datas) > 0:
				break

			sleep(0.2)

		self._cleanup_divs()

	def ask(self, message: str) -> str:
		"""
		Send a message to chatGPT and return the response.
		Args:
			message (str): The message to send.
		Returns:
			str: The response received from OpenAI.
		"""
		print('In the ask function')
		response = list(self.ask_stream(message))
		return (
			reduce(operator.add, response)
			if len(response) > 0
			else "Unusable response produced by ChatGPT, maybe its unavailable."
		)

	def new_conversation(self):
		self.parent_message_id = str(uuid.uuid4())
		self.conversation_id = None

# --------------------------------------------------------------------------------

	def go_to_page(self, url):
		self.page.goto(url=url if "://" in url else "http://" + url)
		self.client = self.page.context.new_cdp_session(self.page)
		self.page_element_buffer = {}

	def scroll(self, direction):
		if direction == "up":
			self.page.evaluate(
				"(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop - window.innerHeight;"
			)
		elif direction == "down":
			self.page.evaluate(
				"(document.scrollingElement || document.body).scrollTop = (document.scrollingElement || document.body).scrollTop + window.innerHeight;"
			)

	def click(self, id):
		# Inject javascript into the page which removes the target= attribute from all links
		js = """
		links = document.getElementsByTagName("a");
		for (var i = 0; i < links.length; i++) {
			links[i].removeAttribute("target");
		}
		"""
		self.page.evaluate(js)

		element = self.page_element_buffer.get(int(id))
		if element:
			x = element.get("center_x")
			y = element.get("center_y")
			
			self.page.mouse.click(x, y)
		else:
			print("Could not find element")

	def type(self, id, text):
		self.click(id)
		self.page.keyboard.type(text)

	def enter(self):
		self.page.keyboard.press("Enter")

	def crawl(self):
		page = self.page
		page_element_buffer = self.page_element_buffer
		start = time.time()

		page_state_as_text = []

		device_pixel_ratio = page.evaluate("window.devicePixelRatio")
		if platform == "darwin" and device_pixel_ratio == 1:  # lies
			device_pixel_ratio = 2

		win_scroll_x 		= page.evaluate("window.scrollX")
		win_scroll_y 		= page.evaluate("window.scrollY")
		win_upper_bound 	= page.evaluate("window.pageYOffset")
		win_left_bound 		= page.evaluate("window.pageXOffset") 
		win_width 			= page.evaluate("window.screen.width")
		win_height 			= page.evaluate("window.screen.height")
		win_right_bound 	= win_left_bound + win_width
		win_lower_bound 	= win_upper_bound + win_height
		document_offset_height = page.evaluate("document.body.offsetHeight")
		document_scroll_height = page.evaluate("document.body.scrollHeight")

#		percentage_progress_start = (win_upper_bound / document_scroll_height) * 100
#		percentage_progress_end = (
#			(win_height + win_upper_bound) / document_scroll_height
#		) * 100
		percentage_progress_start = 1
		percentage_progress_end = 2

		page_state_as_text.append(
			{
				"x": 0,
				"y": 0,
				"text": "[scrollbar {:0.2f}-{:0.2f}%]".format(
					round(percentage_progress_start, 2), round(percentage_progress_end)
				),
			}
		)

		tree = self.client.send(
			"DOMSnapshot.captureSnapshot",
			{"computedStyles": [], "includeDOMRects": True, "includePaintOrder": True},
		)
		strings	 	= tree["strings"]
		document 	= tree["documents"][0]
		nodes 		= document["nodes"]
		backend_node_id = nodes["backendNodeId"]
		attributes 	= nodes["attributes"]
		node_value 	= nodes["nodeValue"]
		parent 		= nodes["parentIndex"]
		node_types 	= nodes["nodeType"]
		node_names 	= nodes["nodeName"]
		is_clickable = set(nodes["isClickable"]["index"])

		text_value 			= nodes["textValue"]
		text_value_index 	= text_value["index"]
		text_value_values 	= text_value["value"]

		input_value 		= nodes["inputValue"]
		input_value_index 	= input_value["index"]
		input_value_values 	= input_value["value"]

		input_checked 		= nodes["inputChecked"]
		layout 				= document["layout"]
		layout_node_index 	= layout["nodeIndex"]
		bounds 				= layout["bounds"]

		cursor = 0
		html_elements_text = []

		child_nodes = {}
		elements_in_view_port = []

		anchor_ancestry = {"-1": (False, None)}
		button_ancestry = {"-1": (False, None)}

		def convert_name(node_name, has_click_handler):
			if node_name == "a":
				return "link"
			if node_name == "input":
				return "input"
			if node_name == "img":
				return "img"
			if (
				node_name == "button" or has_click_handler
			):  # found pages that needed this quirk
				return "button"
			else:
				return "text"

		def find_attributes(attributes, keys):
			values = {}

			for [key_index, value_index] in zip(*(iter(attributes),) * 2):
				if value_index < 0:
					continue
				key = strings[key_index]
				value = strings[value_index]

				if key in keys:
					values[key] = value
					keys.remove(key)

					if not keys:
						return values

			return values

		def add_to_hash_tree(hash_tree, tag, node_id, node_name, parent_id):
			parent_id_str = str(parent_id)
			if not parent_id_str in hash_tree:
				parent_name = strings[node_names[parent_id]].lower()
				grand_parent_id = parent[parent_id]

				add_to_hash_tree(
					hash_tree, tag, parent_id, parent_name, grand_parent_id
				)

			is_parent_desc_anchor, anchor_id = hash_tree[parent_id_str]

			# even if the anchor is nested in another anchor, we set the "root" for all descendants to be ::Self
			if node_name == tag:
				value = (True, node_id)
			elif (
				is_parent_desc_anchor
			):  # reuse the parent's anchor_id (which could be much higher in the tree)
				value = (True, anchor_id)
			else:
				value = (
					False,
					None,
				)  # not a descendant of an anchor, most likely it will become text, an interactive element or discarded

			hash_tree[str(node_id)] = value

			return value

		for index, node_name_index in enumerate(node_names):
			node_parent = parent[index]
			node_name = strings[node_name_index].lower()

			is_ancestor_of_anchor, anchor_id = add_to_hash_tree(
				anchor_ancestry, "a", index, node_name, node_parent
			)

			is_ancestor_of_button, button_id = add_to_hash_tree(
				button_ancestry, "button", index, node_name, node_parent
			)

			try:
				cursor = layout_node_index.index(
					index
				)  # todo replace this with proper cursoring, ignoring the fact this is O(n^2) for the moment
			except:
				continue

			if node_name in black_listed_elements:
				continue

			[x, y, width, height] = bounds[cursor]
			x /= device_pixel_ratio
			y /= device_pixel_ratio
			width /= device_pixel_ratio
			height /= device_pixel_ratio

			elem_left_bound = x
			elem_top_bound = y
			elem_right_bound = x + width
			elem_lower_bound = y + height

			partially_is_in_viewport = (
				elem_left_bound < win_right_bound
				and elem_right_bound >= win_left_bound
				and elem_top_bound < win_lower_bound
				and elem_lower_bound >= win_upper_bound
			)

			if not partially_is_in_viewport:
				continue

			meta_data = []

			# inefficient to grab the same set of keys for kinds of objects but its fine for now
			element_attributes = find_attributes(
				attributes[index], ["type", "placeholder", "aria-label", "title", "alt"]
			)

			ancestor_exception = is_ancestor_of_anchor or is_ancestor_of_button
			ancestor_node_key = (
				None
				if not ancestor_exception
				else str(anchor_id)
				if is_ancestor_of_anchor
				else str(button_id)
			)
			ancestor_node = (
				None
				if not ancestor_exception
				else child_nodes.setdefault(str(ancestor_node_key), [])
			)

			if node_name == "#text" and ancestor_exception:
				text = strings[node_value[index]]
				if text == "|" or text == "•":
					continue
				ancestor_node.append({
					"type": "type", "value": text
				})
			else:
				if (
					node_name == "input" and element_attributes.get("type") == "submit"
				) or node_name == "button":
					node_name = "button"
					element_attributes.pop(
						"type", None
					)  # prevent [button ... (button)..]
				
				for key in element_attributes:
					if ancestor_exception:
						ancestor_node.append({
							"type": "attribute",
							"key":  key,
							"value": element_attributes[key]
						})
					else:
						meta_data.append(element_attributes[key])

			element_node_value = None

			if node_value[index] >= 0:
				element_node_value = strings[node_value[index]]
				if element_node_value == "|": #commonly used as a seperator, does not add much context - lets save ourselves some token space
					continue
			elif (
				node_name == "input"
				and index in input_value_index
				and element_node_value is None
			):
				node_input_text_index = input_value_index.index(index)
				text_index = input_value_values[node_input_text_index]
				if node_input_text_index >= 0 and text_index >= 0:
					element_node_value = strings[text_index]

			# remove redudant elements
			if ancestor_exception and (node_name != "a" and node_name != "button"):
				continue

			elements_in_view_port.append(
				{
					"node_index": str(index),
					"backend_node_id": backend_node_id[index],
					"node_name": node_name,
					"node_value": element_node_value,
					"node_meta": meta_data,
					"is_clickable": index in is_clickable,
					"origin_x": int(x),
					"origin_y": int(y),
					"center_x": int(x + (width / 2)),
					"center_y": int(y + (height / 2)),
				}
			)

		# lets filter further to remove anything that does not hold any text nor has click handlers + merge text from leaf#text nodes with the parent
		elements_of_interest= []
		id_counter 			= 0

		for element in elements_in_view_port:
			node_index = element.get("node_index")
			node_name = element.get("node_name")
			node_value = element.get("node_value")
			is_clickable = element.get("is_clickable")
			origin_x = element.get("origin_x")
			origin_y = element.get("origin_y")
			center_x = element.get("center_x")
			center_y = element.get("center_y")
			meta_data = element.get("node_meta")

			inner_text = f"{node_value} " if node_value else ""
			meta = ""
			
			if node_index in child_nodes:
				for child in child_nodes.get(node_index):
					entry_type = child.get('type')
					entry_value= child.get('value')

					if entry_type == "attribute":
						entry_key = child.get('key')
						meta_data.append(f'{entry_key}="{entry_value}"')
					else:
						inner_text += f"{entry_value} "

			if meta_data:
				meta_string = " ".join(meta_data)
				meta = f" {meta_string}"

			if inner_text != "":
				inner_text = f"{inner_text.strip()}"

			converted_node_name = convert_name(node_name, is_clickable)

			# not very elegant, more like a placeholder
			if (
				(converted_node_name != "button" or meta == "")
				and converted_node_name != "link"
				and converted_node_name != "input"
				and converted_node_name != "img"
				and converted_node_name != "textarea"
			) and inner_text.strip() == "":
				continue

			page_element_buffer[id_counter] = element

			if inner_text != "": 
				elements_of_interest.append(
					f"""<{converted_node_name} id={id_counter}{meta}>{inner_text}</{converted_node_name}>"""
				)
			else:
				elements_of_interest.append(
					f"""<{converted_node_name} id={id_counter}{meta}/>"""
				)
			id_counter += 1

		print("Parsing time: {:0.2f} seconds".format(time.time() - start))
		return elements_of_interest

if (
	__name__ == "__main__"
):
	_crawler = Crawler()
	openai.api_key = "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"

	def print_help():
		print(
			"(g) to visit url\n(u) scroll up\n(d) scroll down\n(c) to click\n(t) to type\n" +
			"(h) to view commands again\n(r/enter) to run suggested command\n(o) change objective"
		)

	def get_gpt_command(objective, url, previous_command, browser_content):
		prompt = prompt_template
		prompt = prompt.replace("$objective", objective)
		prompt = prompt.replace("$url", url[:100])
		prompt = prompt.replace("$previous_command", previous_command)
		prompt = prompt.replace("$browser_content", browser_content[:4500])
		print('A new tab should have opened')
		_crawler.new_tab()
		# placeholder while trying to get chatgpt to give a response
		response = _crawler.ask('who is King Louis 7th?')
		print('Response here: ', response)
		# response = openai.Completion.create(model="text-davinci-002", prompt=prompt, temperature=0.5, best_of=10, n=3, max_tokens=50)
		# bot = ChatGPT()
		# response = bot.ask('is New York state richer than California?')
		# print(response)
		# response = subprocess.run("chatgpt", "is New York state richer than California?", "dirB")
		# print ('response: ', response.choices[0].text)
		# return response.choices[0].text
		return 'temp'

	def run_cmd(cmd):
		cmd = cmd.split("\n")[0]

		if cmd.startswith("SCROLL UP"):
			_crawler.scroll("up")
		elif cmd.startswith("SCROLL DOWN"):
			_crawler.scroll("down")
		elif cmd.startswith("CLICK"):
			commasplit = cmd.split(",")
			id = commasplit[0].split(" ")[1]
			_crawler.click(id)
		elif cmd.startswith("TYPE"):
			spacesplit = cmd.split(" ")
			id = spacesplit[1]
			text = spacesplit[2:]
			text = " ".join(text)
			# Strip leading and trailing double quotes
			text = text[1:-1]

			if cmd.startswith("TYPESUBMIT"):
				text += '\n'
			_crawler.type(id, text)
		elif cmd.startswith("ANSWER"):
			print('Here: ', cmd)
			exit(0)

		time.sleep(2)

	objective = "Make a reservation for 2 at 7pm at bistro vida in menlo park"
	print("\nWelcome to natbot! What is your objective?")
	i = input()
	if len(i) > 0:
		objective = i

	gpt_cmd = ""
	prev_cmd = ""
	_crawler.go_to_page("google.com")
	try:
		while True:
			browser_content = "\n".join(_crawler.crawl())
			prev_cmd = gpt_cmd
			gpt_cmd = get_gpt_command(objective, _crawler.page.url, prev_cmd, browser_content)
			gpt_cmd = gpt_cmd.strip()

			if not quiet:
				print("URL: " + _crawler.page.url)
				print("Objective: " + objective)
				print("----------------\n" + browser_content + "\n----------------\n")
			if len(gpt_cmd) > 0:
				print("Suggested command: " + gpt_cmd)


			command = input()
			if command == "r" or command == "":
				run_cmd(gpt_cmd)
			elif command == "g":
				url = input("URL:")
				_crawler.go_to_page(url)
			elif command == "u":
				_crawler.scroll("up")
				time.sleep(1)
			elif command == "d":
				_crawler.scroll("down")
				time.sleep(1)
			elif command == "c":
				id = input("id:")
				_crawler.click(id)
				time.sleep(1)
			elif command == "t":
				id = input("id:")
				text = input("text:")
				_crawler.type(id, text)
				time.sleep(1)
			elif command == "o":
				objective = input("Objective:")
			else:
				print_help()
	except KeyboardInterrupt:
		print("\n[!] Ctrl+C detected, exiting gracefully.")
		exit(0)