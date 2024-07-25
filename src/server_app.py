#
# demo application for http3_server.py
#

import datetime
import os
from urllib.parse import urlencode

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.types import Receive, Scope, Send

ROOT = os.path.dirname(__file__)
STATIC_ROOT = os.environ.get("STATIC_ROOT", os.path.join(ROOT, "htdocs"))
STATIC_URL = "/"

templates = Jinja2Templates(directory=os.path.join(ROOT, "templates"))


async def homepage(request):
    """
    Simple homepage.
    """
    return templates.TemplateResponse("client_pyscript.html", {"request": request})


async def wasm_python_code(request):
    """
    Simple homepage.
    """
    return templates.TemplateResponse("client_main.py", {"request": request})

""" START
"""

db = { }  

# CREATE
async def do_POST(request):
    print(">> do_POST() activated")

    content = await request.json()

    key = list(content.keys())[0]
    value = list(content.values())[0]

    global db
    if key in db :
        print(':: CREATE {}:{} rejected'.format(key, value))
        content = 'CREATE rejected'
    else:
        db[key] = value

        print(':: CREATE {}:{} created'.format(key, value))
        content = 'CREATE accpeted'

    media_type = request.headers.get("content-type")
    return Response(content, media_type=media_type)

# READ
async def do_GET(request):
    print(">> do_GET() activated")

    key = request.path_params["key"]    

    global db
    if key in db:
        print(':: READ {}:{} completed'.format(key, db[key]))
        content = 'READ accepted for < {} : {} >'.format(key, db[key])
    else:
        print(':: READ {} rejected'.format(key))
        content = 'READ rejected'
    
    media_type = request.headers.get("content-type")
    return Response(content, media_type=media_type)

# UPDATE
async def do_PUT(request):
    print(">> do_PUT() activated")

    content = await request.json()

    key = list(content.keys())[0]
    value = list(content.values())[0]

    global db
    if key in db :
        db[key] = value

        print(':: UPDATE {}:{} completed'.format(key, value))
        content = 'UPDATE completed'
    else:
        print(':: UPDATE {}:{} rejected'.format(key, value))
        content = 'UPDATE rejected'
    
    media_type = request.headers.get("content-type")
    return Response(content, media_type=media_type)

# DELETE
async def do_DELETE(request):
    print(">> do_DELETE() activated")

    key = request.path_params["key"]    

    global db
    if key in db:
        del db[key]

        print(':: DELETE {} completed'.format(key))
        content = 'DELETE accepted'
    else:
        print(':: DELETE {} rejected'.format(key))
        content = 'DELETE rejected'
    
    media_type = request.headers.get("content-type")
    return Response(content, media_type=media_type)

""" END
"""

starlette = Starlette(
    routes=[
        Route("/", homepage),
        Route("/wasm/client_main.py", wasm_python_code),

        Route("/membership_api/{key:str}", do_GET),
        Route("/membership_api/{key:str}", do_POST, methods=["POST"]),
        Route("/membership_api/{key:str}", do_PUT, methods=["PUT"]),
        Route("/membership_api/{key:str}", do_DELETE, methods=["DELETE"]),

        Mount(STATIC_URL, StaticFiles(directory=STATIC_ROOT, html=True)),
    ]
)

async def run(scope: Scope, receive: Receive, send: Send) -> None:
    await starlette(scope, receive, send)
