from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import os
import logging
import json


# Initialize FastAPI
app = FastAPI()

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@app.get("/test")
async def call_test():
    logger.info('call_test')
    return JSONResponse(content={"status": "ok"})


def save_user_session(user_id, session):
    logger.info(f'save_user_session: {user_id}')
    # Save the user json file
    path = './data/users'
    user_path = os.path.join(path, f'{user_id}.json')
    json.dump(session, open(user_path, 'w'))


def get_user_session(user_id):
    logger.info(f'get_user_session: {user_id}')
    
    # Check is the usef json file exist
    path = './data/users'
    user_path = os.path.join(path, f'{user_id}.json')    
    if not os.path.exists(user_path):
        default_path = os.path.join(path, 'default.json')
        session = json.load(open(default_path, 'r'))
        # Save the user json file
        save_user_session(user_id, session)

    session = json.load(open(user_path, 'r'))
    # Return the user json file as dict
    return session


def log_message(message):
    logger.info(f'message: {message}')
    # Read the chat id from the message
    chat_id = message['chat']['id']
    # Prepare a folder
    path = f'./data/chats/{chat_id}'
    os.makedirs(path, exist_ok=True)
    filename = f'{message["date"]}_{message["message_id"]}.json'
    # Save the user json file
    file_path = os.path.join(path, filename)
    json.dump(message, open(file_path, 'w'))


@app.post("/message")
async def call_message(request: Request):
    logger.info('call_message')
    message = await request.json()
    logger.info(message)
    """
    INFO:server:{
       'message_id': 22,
       'from': {
            'id': 106129214, 
            'is_bot': False, 
            'first_name': 'Alex', 
            'username': 'format37', 
            'language_code': 'en', 
            'is_premium': True
         }, 
        'chat': {
            'id': 106129214, 
            'first_name': 'Alex', 
            'username': 'format37', 
            'type': 'private'
        }, 
        'date': 1698311200, 
        'text': '9'
    }
    """
    user_session = get_user_session(message['from']['id'])
    log_message(message)
    logger.info(f'user_session: {user_session}')
    return JSONResponse(content={"status": "ok"})
