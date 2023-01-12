from playwright.sync_api import sync_playwright
import time
import sys
from sys import argv, exit, platform 
import openai
import os
from dotenv import load_dotenv, find_dotenv
from ast import literal_eval

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
EXAMPLE BROWSER CONTENT:
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

	# session_div_id = "chatgpt-wrapper-session-data"

	def __init__(self):
		self.browser = (
      sync_playwright()
      .start()
			.chromium.launch(headless=False)
		)

		self.context = self.browser.new_context()
		self.page = self.context.new_page()

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
		url = tree["strings"][0]
		print("url", url)
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
		elements_of_interest.append(url)
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

def natbot():
	_crawler = Crawler()
	load_dotenv(find_dotenv())
	openai.api_key = os.getenv('openai_api_key')

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
		# print('A new tab should have opened')
		# _crawler.new_tab()
		# placeholder while trying to get chatgpt to give a response
		# response = _crawler.ask('who is King Louis 7th?')
		# print('Response here: ', response)
		response = openai.Completion.create(model="text-davinci-003", prompt=prompt, temperature=0.5, best_of=10, n=3, max_tokens=50)
		# bot = ChatGPT()
		# response = bot.ask('is New York state richer than California?')
		# print(response)
		# response = subprocess.run("chatgpt", "is New York state richer than California?", "dirB")
		# print ('response: ', response.choices[0].text)
		return response.choices[0].text
		# return 'temp'

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
    # Change this to exit when ANSWER is the gpt_cmd
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

question_prompt_template = """
You have been given:
	(1) a question that you are trying to answer
	(2) a simplified text description of what's visible in the browser window (more on that below)

You should answer the question based on the browser content.

The format of the browser content is highly simplified; all formatting elements are stripped.
Interactive elements such as links, inputs, buttons are represented like this:
		<link id=1>text</link>
		<button id=2>text</button>
		<input id=3>text</input>
Images are rendered as their alt text like this:
		<img id=4 alt=""/>

Here are some examples:
EXAMPLE 1:
==================================================
EXAMPLE BROWSER CONTENT:
------------------
<button id=0 Accessibility Menu/>
<img id=1 Open the Accessibility Menu/>
<link id=2>Skip to main content</link>
<link id=3>Contact Us</link>
<link id=4>Quick Links</link>
<link id=5>Staff Directory</link>
<text id=6>Powered by</text>
<link id=7 alt="Google Translate">Translate</link>
<link id=8 alt="Brookfield High School"/>
<link id=9>Our Schools</link>
<link id=10>About Us</link>
<link id=11>Academics</link>
<link id=12>Faculty / Staff</link>
<link id=13>Family</link>
<link id=14>Students</link>
<link id=15>Search</link>
<link id=16 title="Display a printer-friendly version of this page."/>
<link id=17 alt="Share page with AddThis"/>
<text id=18>You are here</text>
<link id=19>Home</link>
<text id=20>››</text>
<link id=21>Brookfield High School</link>
<text id=22>Brookfield High School Staff Directory</text>
<text id=23>Other Directories</text>
<link id=24>District</link>
<text id=25>|</text>
<link id=26>Whisconier Middle School</link>
<text id=27>|</text>
<link id=28>Huckleberry Hill Elementary School</link>
<text id=29>|</text>
<link id=30>Center Elementary School</link>
<link id=31>Administration</link>
<text id=32>Name</text>
<text id=33>Title</text>
<text id=34>Phone</text>
<text id=35>Website</text>
<link id=36>Marc Balanda</link>
<text id=37>Principal</text>
<text id=38>(203) 775-7725 ext. 7730</text>
<link id=39>Susan Griffin</link>
<text id=40>(grades 10 & 12)</text>
<text id=41>Assistant Principal</text>
<text id=42>(203) 775-7725 ext. 7733</text>
<link id=43>Jules Scheithe</link>
<text id=44>(grades 9 & 11)</text>
<text id=45>Assistant Principal</text>
<text id=46>(203) 775-7725 ext. 7760</text>
<text id=47>Administrative Support Staff</text>
<text id=48>Name</text>
<text id=49>Title</text>
<text id=50>Phone</text>
<text id=51>Website</text>
<link id=52>Carol Ann D'Arcangelo</link>
<text id=53>Administrative Secretary to the Principal</text>
<text id=54>(203) 775-7725 ext. 7731</text>
------------------
QUESTION: Who is the secretary to the principal?
YOUR ANSWER: Carol Ann D'Arcangelo

The current browser content, the question you are answering follow. Reply with your answer.
CURRENT BROWSER CONTENT:
------------------
$browser_content
------------------
QUESTION: $question
YOUR ANSWER:
"""

class Crawler2:
  def __init__(self):
    self.browser = (
      sync_playwright()
      .start()
		  .chromium.launch(headless=False)
		)
    self.context = self.browser.new_context()
    self.page = self.context.new_page()

  def qa_go_to_page(self, url):
      self.page.set_default_timeout(120000)
      self.page.goto(url=url if "://" in url else "http://" + url)
      self.client = self.page.context.new_cdp_session(self.page)
      self.page_element_buffer = {}

  def crawl(self, url):
      Crawler2.qa_go_to_page(self, url)
      page = self.page
      client = page.context.new_cdp_session(self.page)
      page_element_buffer = {}
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

      tree = client.send(
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

        # [x, y, width, height] = bounds[cursor]
        # x /= device_pixel_ratio
        # y /= device_pixel_ratio
        # width /= device_pixel_ratio
        # height /= device_pixel_ratio

        # elem_left_bound = x
        # elem_top_bound = y
        # elem_right_bound = x + width
        # elem_lower_bound = y + height

        # partially_is_in_viewport = (
        # 	elem_left_bound < win_right_bound
        # 	and elem_right_bound >= win_left_bound
        # 	and elem_top_bound < win_lower_bound
        # 	and elem_lower_bound >= win_upper_bound
        # )

        # if not partially_is_in_viewport:
        # 	continue

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
            # "origin_x": int(x),
            # "origin_y": int(y),
            # "center_x": int(x + (width / 2)),
            # "center_y": int(y + (height / 2)),
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

def question_bot(url):
  _crawler2 = Crawler2()

  def qa_get_gpt_command(question, browser_content):
    prompt = question_prompt_template
    prompt = prompt.replace("$question", question)
    full_response = []
    if len(browser_content) > 5500:
      for i in range(0, len(browser_content), 5500):
        prompt = question_prompt_template
        prompt = prompt.replace("$question", question)
        # print('browser section', i, ': ', browser_content[i:i+5500])
        prompt = prompt.replace("$browser_content", browser_content[i:i+5500])
        # print('prompt section', i, ': ', prompt)
        response = openai.Completion.create(model="text-davinci-003", prompt=prompt, top_p=1, temperature=0.3, best_of=1, n=1, max_tokens=250)
        print("loop", i, response.choices[0].text)
        full_response.append(response.choices[0].text)
      return full_response
    prompt = prompt.replace("$browser_content", browser_content)
    response = openai.Completion.create(model="text-davinci-003", prompt=prompt, top_p=1, temperature=0.3, best_of=1, n=1, max_tokens=250)
    return response.choices[0].text
  
  qa_gpt_cmd = ""
  question = ""
  print("\nWelcome to Q&A bot! What is your question?")
  i = input()
  if len(i) > 0:
    question = i

  try:
    while True:
      browser_content = "\n".join(_crawler2.crawl(url=url))
      qa_gpt_cmd = qa_get_gpt_command(question, browser_content)

      print("Question: " + question)
      # print("----------------\n" + browser_content + "\n----------------\n")
      if len(qa_gpt_cmd) > 0:
        print("Suggested command: ", qa_gpt_cmd)
      
      command = input()
  except KeyboardInterrupt:
    print("\n[!] Ctrl+C detected, exiting gracefully.")
    exit(0)

def main():
  load_dotenv(find_dotenv())
  openai.api_key = os.getenv('openai_api_key')
  # print("\nWelcome! What is your question?")
  # Give me a list of 3 high schools in Fairfield County, CT
  # i = input()
  # prompt = i
  # response = openai.Completion.create(model="text-davinci-003", prompt=prompt, temperature=0.5, best_of=5, n=1, max_tokens=250)
  # print(response.choices[0].text)
  # print('Waiting...')
  # Find the staff directory for Fairfield County, CT and return the url for that page
  # i2 = input()
  # prompt2 = i2
  # response2 = openai.Completion.create(model="text-davinci-003", prompt=prompt2, temperature=0.5, best_of=5, n=1, max_tokens=250)
  # Give me the url for staff directory of brookfield high school, CT
  # url = natbot()
  # url = 'https://www.brookfield.k12.ct.us/brookfield-high-school/pages/brookfield-high-school-staff-directory'
  url = 'https://www.stamfordhigh.org/connect/staff-directory'
  question_bot(url)

  # pipe the url into the Q&A page scraping version of natbot we have 

def davinci(prompt):
	prompt_template = """
		Your job is to be a Q&A bot that returns the answer as a python string that is comma delimited. Your answer should be as concise as possible.

		Do not put the word Answer or any other word or characters before your answer. 

		Example #1. Who were the last three presidents of the united states?
		George W. Bush, Barack Obama, Donald Trump

		Example #2. What is the capital of the United States?
		Washington, D.C.

		Example #3. Which countries are the largest by GDP?
		United States, China, Japan, Germany, United Kingdom, France, India, Brazil, Italy, Canada

		#####################################
		Question: {question}
	"""
	prompt_template = prompt_template.replace("{question}", prompt)
	response = openai.Completion.create(model="text-davinci-003", prompt=prompt_template, temperature=0.5, best_of=5, n=1, max_tokens=250)
	res = response.choices[0].text.split(",")
	res = [x.strip() for x in res]
	return res

def load_keys():
	load_dotenv(find_dotenv())
	openai.api_key = os.getenv('openai_api_key')

def main():
	print("\nWelcome! Firing up the high school bot")
	load_keys()
	high_school_prompt = "What are the names of 100 high schools in Fairfield County, CT?"
	high_schools = davinci(high_school_prompt)
	print(high_schools)
	# arr = ['Amity Regional High School', ' Brien McMahon High School', ' Brookfield High School', ' Bullard-Havens Technical High School', ' Central High School', ' Danbury High School', ' Darien High School', ' Fairfield Ludlowe High School', ' Fairfield Warde High School', ' Greenwich High School', ' Harding High School', ' Joel Barlow High School', ' Kolbe Cathedral High School', ' Lauralton Hall', ' Masuk High School', ' McMahon High School', ' New Canaan High School', ' New Fairfield High School', ' Newtown High School', ' Norwalk High School', ' Notre Dame Catholic High School', ' Platt Technical High School', ' Pomperaug High School', ' Ridgefield High School', ' Sacred Heart Academy', ' Shepaug Valley High School', ' Staples High School', ' Stratford High School', ' Trumbull High School', ' Weston High School', ' Wilton High School', ' Abbott Tech', ' Ansonia High School', ' Bassick High School', ' Bethel High School', ' Brookfield High School', ' Bunnell High School', ' Bullard-Havens Technical High School', ' Central High School', ' Cheney Tech', ' Danbury High School', ' Derby High School', ' East Catholic High School', ' East Haven High School', ' Fairfield Ludlowe High School', ' Fairfield Warde High School']
	# arr2 = ['Answer: George Washington', ' John Adams', ' Thomas Jefferson', ' James Madison', ' James Monroe', ' John Quincy Adams', ' Andrew Jackson', ' Martin Van Buren', ' William Henry Harrison', ' John Tyler', ' James K. Polk', ' Zachary Taylor', ' Millard Fillmore', ' Franklin Pierce', ' James Buchanan', ' Abraham Lincoln', ' Andrew Johnson', ' Ulysses S. Grant', ' Rutherford B. Hayes', ' James A. Garfield', ' Chester A. Arthur', ' Grover Cleveland', ' Benjamin Harrison', ' William McKinley', ' Theodore Roosevelt', ' William Howard Taft', ' Woodrow Wilson', ' Warren G. Harding', ' Calvin Coolidge', ' Herbert Hoover', ' Franklin D. Roosevelt', ' Harry S. Truman', ' Dwight D. Eisenhower', ' John F. Kennedy', ' Lyndon B. Johnson', ' Richard Nixon', ' Gerald Ford', ' Jimmy Carter', ' Ronald Reagan', ' George H. W. Bush', ' Bill Clinton', ' George W. Bush', ' Barack Obama', ' Donald Trump']

if __name__ == "__main__":
  main()