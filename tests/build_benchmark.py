"""Author-created course regression set, not an external exam or training data.

Answers and references are never loaded by the solver. Freeze before model evaluation.
"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# topic, PDF page, question, four options, correct original indices (zero based)
ROWS = [
('1-Introduction',9,'Who invented the World Wide Web?', ['Tim Berners-Lee','Vint Cerf','Brendan Eich','Linus Torvalds'],[0]),
('1-Introduction',20,'What does a network protocol define?', ['Formats and rules for exchanging messages','Only the screen resolution','Only database table names','The price of Internet access'],[0]),
('1-Introduction',24,'What is the role of a domain name?', ['A memorable name for an Internet node','A CSS class selector','An HTML closing tag','A JavaScript loop'],[0]),
('1-Introduction',39,'Which protocol is used for communication between a Web client and Web server?', ['HTTP','HTML','CSS','SQL'],[0]),
('1-Introduction',40,'Which is a markup language rather than a communication protocol?', ['HTML','HTTP','TCP','IP'],[0]),
('1-Introduction',44,'A web browser normally acts as which participant in the client-server model?', ['Client','Database server','DNS root server','Compiler'],[0]),
('1-Introduction',48,'What does URL stand for?', ['Uniform Resource Locator','Universal Routing Language','Unified Rendering Layer','User Request List'],[0]),
('1-Introduction',57,'Which statement distinguishes Web 2.0 in the lecture?', ['Users create, organize and remix content','Users can only read static content','It replaces HTTP with SQL','It requires every page to be a PDF'],[0]),
('2-HTML',7,'Where is the DOCTYPE declaration placed in an HTML document?', ['At the beginning','Inside the last paragraph','After the closing html tag','Only inside a CSS file'],[0]),
('2-HTML',10,'Select all direct children of the html element in the basic document structure.', ['head','body','tr','li'],[0,1]),
('2-HTML',11,'How many levels of HTML headings are available?', ['Six','Four','Seven','One'],[0]),
('2-HTML',12,'Which HTML element inserts a line break?', ['<br>','<hr>','<p>','<h1>'],[0]),
('2-HTML',15,'Select all formal HTML list categories named in the lecture.', ['Ordered list','Unordered list','Description list','Linear list'],[0,1,2]),
('2-HTML',15,'Which HTML tag defines a list item in ordered and unordered lists?', ['<li>','<ul>','<ol>','<dt>'],[0]),
('2-HTML',22,'Which HTML element creates a hyperlink?', ['<a>','<link>','<url>','<href>'],[0]),
('2-HTML',22,'Thuộc tính nào của thẻ a chỉ định địa chỉ liên kết?', ['href','src','alt','class'],[0]),
('2-HTML',27,'Which attribute specifies the source file of an img element?', ['src','href','target','lang'],[0]),
('2-HTML',29,'Which HTML element represents a row in a table?', ['<tr>','<td>','<th>','<table>'],[0]),
('3-CSS',3,'What is the main purpose of CSS?', ['Define the style and layout of HTML documents','Execute SQL queries','Transfer IP packets','Replace all HTML structure'],[0]),
('3-CSS',4,'Select all CSS styles described in the lecture.', ['Inline','Embedded/internal','External','Relational'],[0,1,2]),
('3-CSS',9,'What are the two parts of a CSS rule?', ['Selector and declaration','Request and response','Row and column','Host and port'],[0]),
('3-CSS',11,'Which CSS selector matches elements with class highlight?', ['.highlight','#highlight','highlight()','@highlight'],[0]),
('3-CSS',13,'Which CSS selector matches the element with id highlight?', ['#highlight','.highlight','highlight[]','<highlight>'],[0]),
('3-CSS',28,'Thuộc tính CSS nào thay đổi màu chữ?', ['color','background-color','font-size','text-align'],[0]),
('3-CSS',29,'Which CSS property horizontally aligns text within its containing element?', ['text-align','vertical-align','font-weight','border-collapse'],[0]),
('3-CSS',32,'Select all examples of CSS pseudo-classes shown for hyperlinks.', ['a:hover','a:visited','a:active','a.href'],[0,1,2]),
('4-JavaScript',12,'Which markup loads JavaScript from an external file?', ['<script src="app.js"></script>','<script href="app.js"></script>','<style src="app.js"></style>','<js file="app.js">'],[0]),
('4-JavaScript',17,'Which function converts a numeric string to an integer?', ['parseInt','String','document.write','alert'],[0]),
('4-JavaScript',23,'What is the JavaScript value of "4" + 3 + 1?', ['"431"','8','"71"','"44"'],[0]),
('4-JavaScript',23,'What is the JavaScript value of 4 + 3 + "1"?', ['"71"','8','"431"','"44"'],[0]),
('4-JavaScript',23,'What is the JavaScript value of "35" - 3?', ['32','"353"','38','NaN'],[0]),
('4-JavaScript',42,'Which Date method returns the four-digit year?', ['getFullYear()','getHours()','getMinutes()','getMilliseconds()'],[0]),
('4-JavaScript',53,'Select all changes JavaScript can make through DOM manipulation.', ['Change element content','Change element styles','Add or delete HTML elements','Change the physical size of the monitor'],[0,1,2]),
('4-JavaScript',57,'Which event fires when a user clicks an HTML element?', ['onclick','onload','onkeydown','onchange'],[0]),
('4-JavaScript',57,'Which event fires when the browser has finished loading the page?', ['onload','onclick','onkeydown','onchange'],[0]),
('4-JavaScript',60,'Which input type masks the characters entered for a password?', ['password','text','submit','reset'],[0]),
('6-NodeJS',4,'Node.js is built on which JavaScript engine?', ['V8','Jinja2','MySQL','Webpack'],[0]),
('6-NodeJS',4,'Which statement about Node.js is NOT correct?', ['It can execute JavaScript only inside a browser','It is a JavaScript runtime','It can execute JavaScript on the server','It uses an event-driven architecture'],[0]),
('6-NodeJS',6,'What is central to Node.js non-blocking asynchronous I/O architecture?', ['Event loop','CSS cascade','HTML parser only','Relational schema'],[0]),
('6-NodeJS',18,'Which CommonJS function loads a module in Node.js?', ['require()','render_template()','querySelector()','getFullYear()'],[0]),
('6-NodeJS',18,'Select all built-in Node.js modules named in the lecture.', ['fs','http','url','react'],[0,1,2]),
('6-NodeJS',20,'How does the lecture export a function from a custom CommonJS module?', ['module.exports.sayHello = function() {}','document.exports.sayHello = function() {}','window.route.sayHello = function() {}','app.template.sayHello = function() {}'],[0]),
('6-NodeJS',23,'Which statement describes blocking I/O?', ['Further execution waits until the current operation completes','Every operation always executes at the same instant','It prevents all callbacks from existing','It only changes CSS styles'],[0]),
('6-NodeJS',28,'In fs.readFile(file, (err, data) => {...}), what should be checked before processing data?', ['Whether err exists','Whether data is a CSS selector','Whether the browser supports HTML headings','Whether the URL ends in .pdf'],[0]),
('7-Front-end dev with NodeJS',11,'Which front-end framework in the lecture was developed by Google?', ['Angular','React','Flask','Node.js'],[0]),
('7-Front-end dev with NodeJS',11,'Select all front-end libraries or frameworks listed in the lecture.', ['React','Vue.js','Angular','MySQL'],[0,1,2]),
('7-Front-end dev with NodeJS',17,'What is Webpack used for in the sample front-end project?', ['Bundling front-end code','Managing database users','Serving as the Python interpreter','Replacing the HTTP protocol'],[0]),
('7-Front-end dev with NodeJS',17,'Which Webpack configuration property identifies the input file to bundle?', ['entry','output.filename','output.path','server.port'],[0]),
('7-Front-end dev with NodeJS',19,'What kind of architecture does React use for reusable independent UI parts?', ['Component-based','Only relational tables','Only operating-system processes','Only static PDF pages'],[0]),
('7-Front-end dev with NodeJS',19,'Which description of React is incorrect?', ['A Python database driver','A JavaScript UI library','Uses reusable components','Used for single-page applications'],[0]),
('8-Python Flask',3,'Flask là framework web dành cho ngôn ngữ nào?', ['Python','Java','PHP','C++'],[0]),
('8-Python Flask',3,'Why is Flask described as a micro framework?', ['It is lightweight and does not require a particular set of tools or libraries','It cannot serve HTTP requests','It is only a CSS preprocessor','It includes every possible feature by default'],[0]),
('8-Python Flask',5,'Which template engine is named in the Flask lecture?', ['Jinja2','V8','Webpack','MongoDB'],[0]),
('8-Python Flask',7,'Which command installs Flask?', ['pip install flask','npm install flask','python remove flask','mysql create flask'],[0]),
('8-Python Flask',8,'Which decorator maps the homepage URL to a Flask function?', ["@app.route('/')","@app.css('/')","@app.database('/')","@app.template('/')"],[0]),
('8-Python Flask',9,'Which port is used to access the Flask development app in the lecture?', ['5000','3000','3306','53'],[0]),
('8-Python Flask',11,'What does routing mean in Flask?', ['Mapping URLs to specific code functions','Sorting CSS declarations alphabetically','Turning Python objects into database tables','Choosing the color of hyperlinks'],[0]),
('9-Database',4,'Select all relational databases named in the lecture.', ['MySQL','PostgreSQL','SQLite','MongoDB'],[0,1,2]),
('9-Database',4,'Select all NoSQL databases named in the lecture.', ['MongoDB','CouchDB','MySQL','SQLite'],[0,1]),
('9-Database',4,'How do relational databases represent structured data?', ['Tables with relationships','Only CSS rules','Only JavaScript callbacks','Only image pixels'],[0]),
('9-Database',5,'Which database category is identified as suitable for structured transactional applications?', ['Relational database','Only schema-less document stores','An HTML unordered list','A CSS stylesheet'],[0]),
('9-Database',9,'What does SQLAlchemy ORM map Python objects to?', ['Database tables','CSS pseudo-classes','Network packet headers','Browser tabs'],[0]),
('9-Database',9,'Select all benefits of ORM stated in the lecture.', ['Reduces the need to write raw SQL','Makes switching database types easier','Eliminates every possible database error','Removes the need for data storage'],[0,1]),
('9-Database',13,'Which extension is named for creating forms in Flask?', ['Flask-WTF','React','V8','Webpack'],[0]),
]


def main():
    rng = random.Random(24092026)
    data = []
    for i, (topic, page, question, choices, indices) in enumerate(ROWS, 1):
        order = list(range(4))
        rng.shuffle(order)
        options = {chr(65 + n): choices[j] for n, j in enumerate(order)}
        answer = ', '.join(chr(65 + n) for n, j in enumerate(order) if j in indices)
        data.append({'id': f'course-{i:02}', 'topic': topic, 'source': topic + '.pdf', 'page': page,
                     'question': question, 'choices': options, 'answer': answer,
                     'multi': len(indices) > 1})
    path = ROOT / 'tests/course_benchmark.json'
    if path.exists():
        raise RuntimeError('Benchmark already frozen. Do not silently replace it after evaluation.')
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Frozen {len(data)} course questions at {path}')


if __name__ == '__main__':
    main()
