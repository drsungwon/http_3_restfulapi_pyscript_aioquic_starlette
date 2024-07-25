import pyscript    
from pyscript import document

import asyncio   
import json    
import js

from pyscript.ffi import create_proxy

SERVER_ADDRESS = 'https://127.0.0.1:4433/membership_api/'

async def post_request(url, parameter):
    r = await js.axios.post(url, parameter)
    if r.status in [200]:
        return [ r.data, r.status, r.statusText ]
    else:
        return {}    

async def get_request(url):
    r = await js.axios.get(url)
    if r.status in [200, 404]:
        # axios Response schema : https://axios-http.com/docs/res_schema
        return [ r.data, r.status, r.statusText ]
    else:
        return {}

async def put_request(url, parameter):
    r = await js.axios.put(url, parameter)
    if r.status in [200, 201, 405, 500]:
        return [ r.data, r.status, r.statusText ]
    else:
        return {}

async def delete_request(url):
    r = await js.axios.delete(url)
    if r.status in [200, 404]:
        return [ r.data, r.status, r.statusText ]
    else:
        return {}
                
async def do_create_by_post(evt): 
    k = document.getElementById("key_create").value
    v = document.getElementById("value_create").value

    url = SERVER_ADDRESS + str(k)
    content = json.dumps({str(k):str(v)})

    document.getElementById("key_create").value = ''
    document.getElementById("value_create").value = ''

    task = asyncio.create_task(post_request(url, content))
    await task
    
    display_msg(["Sends HTTP POST {} with key:value and shows results.".format(SERVER_ADDRESS),
        "{}".format("HTTP POST {} with {}".format(url, content)),
        "{} {}".format(task.result()[1], task.result()[2]),
        "{}".format(task.result()[0])])
                
async def do_read_by_get(evt): 

    k = document.getElementById("key_read").value

    url = SERVER_ADDRESS + str(k)

    document.getElementById("key_read").value = ''

    task = asyncio.create_task(get_request(url))
    await task
    
    display_msg(["Sends HTTP GET {} with key and shows results.".format(SERVER_ADDRESS),
        "{}".format("HTTP GET {}".format(url)),
        "{} {}".format(task.result()[1], task.result()[2]),
        "{}".format(task.result()[0])])
                
async def do_update_by_put(evt): 
    k = document.getElementById("key_update").value
    v = document.getElementById("value_update").value

    url = SERVER_ADDRESS + str(k)
    content = json.dumps({str(k):str(v)})

    document.getElementById("key_update").value = ''
    document.getElementById("value_update").value = ''

    task = asyncio.create_task(put_request(url, content))
    await task
    
    display_msg(["Sends HTTP PUT {} with key:value and shows results.".format(SERVER_ADDRESS),
        "{}".format("HTTP PUT {} with {}".format(url, content)),
        "{} {}".format(task.result()[1], task.result()[2]),
        "{}".format(task.result()[0])])
                
async def do_delete_by_delete(evt): 

    k = document.getElementById("key_delete").value

    url = SERVER_ADDRESS + str(k)

    document.getElementById("key_delete").value = ''

    task = asyncio.create_task(delete_request(url))
    await task
    
    display_msg(["Sends HTTP DELETE {} with key and shows results.".format(SERVER_ADDRESS),
        "{}".format("HTTP DELETE {}".format(url)),
        "{} {}".format(task.result()[1], task.result()[2]),
        "{}".format(task.result()[0])])

def display_msg(msg_list):    
    document.getElementById("out_request").innerText =  "{}".format(msg_list[1])
    document.getElementById("out_response").innerText = "{} - {}".format(msg_list[2], msg_list[3])

if __name__ == '__main__':
    document.getElementById("submit_create").addEventListener("click", create_proxy(do_create_by_post))
    document.getElementById("submit_read").addEventListener("click", create_proxy(do_read_by_get))
    document.getElementById("submit_update").addEventListener("click", create_proxy(do_update_by_put))
    document.getElementById("submit_delete").addEventListener("click", create_proxy(do_delete_by_delete))

    document.getElementById("program_status_1").innerText = 'Please fills key/value and executes menu :'
    document.getElementById("program_status_2").innerText = 'READY'
