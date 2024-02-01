import os
import logging
import json
import requests
import time
import glob

import json
import logging
from pydantic import BaseModel, Field
from langchain.agents import Tool, initialize_agent
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import DocArrayInMemorySearch
from langchain_community.tools import StructuredTool
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.chains import RetrievalQA
import time as py_time
from pathlib import Path


class Panthera:
    
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        # Initialize Llama with your API key and preferred model
        self.llm = ChatOpenAI(
            openai_api_key=os.environ.get('LLM_TOKEN', ''),
            model="gpt-4-0125-preview",
            temperature=0.8
        )
        self.data_dir = './data/chats'
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)  # Ensure data directory exists

    def get_message_type(self, user_session, text):
        if text == '/start':
            return 'cmd'
        elif text == '/configure':
            return 'cmd'
        elif text == '/reset':
            return 'cmd'
        # if user_session['last_cmd'] != 'text':
        # Check the buttons
        with open('data/menu.json') as f:
            menu = json.load(f)
        for key, value in menu.items():
            # logger.info(f'key: {key}, value: {value}')
            if text == key:
                return 'button'
            for button in value['buttons']:
                # logger.info(f'button: {button}')
                if text == button['text']:
                    return 'button'
        return 'text'


    def save_user_session(self, user_id, session):
        self.logger.info(f'save_user_session: {user_id} with cmd: {session["last_cmd"]}')
        # Save the user json file
        path = './data/users'
        user_path = os.path.join(path, f'{user_id}.json')
        json.dump(session, open(user_path, 'w'))


    def get_user_session(self, user_id):
        self.logger.info(f'get_user_session: {user_id}')
        
        # Check is the usef json file exist
        path = './data/users'
        user_path = os.path.join(path, f'{user_id}.json')
        if not os.path.exists(user_path):
            default_path = os.path.join(path, 'default.json')
            session = json.load(open(default_path, 'r'))
            # Save the user json file
            self.save_user_session(user_id, session)

        session = json.load(open(user_path, 'r'))
        # Return the user json file as dict
        return session


    def log_message(self, message):
        self.logger.info(f'message: {message}')
        # Read the chat id from the message
        chat_id = message['chat']['id']
        # Prepare a folder
        path = f'./data/chats/{chat_id}'
        os.makedirs(path, exist_ok=True)
        filename = f'{message["date"]}_{message["message_id"]}.json'
        # Save the user json file
        file_path = os.path.join(path, filename)
        json.dump(message, open(file_path, 'w'))


    def reset_chat(self, chat_id):
        self.logger.info(f'reset_chat: {chat_id}')
        chat_path = f'./data/chats/{chat_id}'
        # Remove all files in chat path
        for f in os.listdir(chat_path):
            self.logger.info(f'remove file: {f}')
            os.remove(os.path.join(chat_path, f))


    def token_counter(self, text, model):
        llm_url = os.environ.get('LLM_URL', '')
        url = f'{llm_url}/token_counter'
        data = {
            "text": text,
            "model": model
        }

        response = requests.post(url, json=data)
        # response = requests.post(url, kwargs=data)
        return response
    
    def default_bot_message(self, message, text):
        current_unix_timestamp = int(time.time())
        self.logger.info(f'default_bot_message: {message}')
        if 'first_name' in message['chat']:
            first_name = message['from']['first_name']
        else:
            first_name = message['from']['username']
        return {
        'message_id': int(message['message_id']) + 1,
        'from': {
                'id': 0, 
                'is_bot': True, 
                'first_name': 'assistant', 
                'username': 'assistant', 
                'language_code': 'en', 
                'is_premium': False
            }, 
            'chat': {
                'id': message['chat']['id'], 
                'first_name': first_name, 
                'username': message['from']['username'], 
                'type': 'private'
            }, 
            'date': current_unix_timestamp, 
            'text': text
        }

    def add_evaluation_to_topic(self, session, topic_name, value=10):
        """
        Function to add an evaluation to a specified topic in a session dictionary.
        
        Args:
        - session (dict): The session dictionary to modify.
        - topic_name (str): The name of the topic to add or modify.
        - date (str): The date for the evaluation. If None, use the current date.
        - value (int): The integer value for the evaluation.
        
        Returns:
        - dict: The modified session dictionary.
        """
        # Ensure "topics" is a dictionary
        if "topics" not in session:
            session["topics"] = {}
        
        # If the topic doesn't exist, add it
        if topic_name not in session["topics"]:
            session["topics"][topic_name] = {"evaluations": []}
        
        # Unix timestamp
        date = int(time.time())
        # Create evaluation dictionary
        evaluation_dict = {"date": date, "value": value}
        
        # Add evaluation to topic
        session["topics"][topic_name]["evaluations"].append(evaluation_dict)
        
        return session
    
    def read_latest_messages(self, user_session, message, system_content=None):
        model = user_session['model']
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        token_limit = 3000
        chat_gpt_prompt = []
        # Fill the prompt
        if system_content is None:
            system_content = "You are the chat member. Your username is assistant. You need to start with 'Assistant:' before each of your messages."
        chat_gpt_prompt_original = [
            {"role": "system", "content": system_content}
        ]
        # if chat_type == 'group' or chat_type == 'supergroup':
        if message['chat']['type'] != 'private':
            self.logger.info("read group chat")
            # Create group id folder in the data path if not exist
            path = os.path.join("data", "chats", str(chat_id))
            # Get all files in folder
            list_of_files = glob.glob(path + "/*.json")
        else:
            self.logger.info("read private chat")
            # Create user id folder in the data path if not exist
            path = os.path.join("data", "chats", str(user_id))
            # Get all files in folder
            list_of_files = glob.glob(path + "/*.json")

        # Sort files by creation time ascending
        list_of_files.sort(key=os.path.getctime, reverse=True)

        # Iterate over sorted files and append message to messages list
        limit_reached = False
        for file_name in list_of_files:
            self.logger.info("reading file: "+file_name)
            prompt_dumped = json.dumps(chat_gpt_prompt)
            if limit_reached == False and \
                self.token_counter(prompt_dumped, model).json()['tokens']<token_limit:
                
                with open(file_name, "r") as f:
                               
                    # Extract the text from the json file
                    # message = json.load(open(os.path.join(path, file), 'r'))
                    message = json.load(f)
                    # Extract the text from the message
                    text = message['text']
                    if message['from']['id']==0:
                        role = 'assistant'                
                    else:
                        role = 'user'
                        user_name = message['from']['first_name']
                        if message['from']['first_name'] == '':
                            user_name = message['from']['username']
                            if message['from']['username'] == '':
                                user_name = 'Unknown'
                        # Add preamble to the message
                        preamble = f'{user_name}: '
                        text = preamble + message['text']

                    chat_gpt_prompt.append({"role": role, "content": text})
            else:
                limit_reached = True
                self.logger.info("token limit reached. removing file: "+file_name)
                os.remove(file_name)

        # Sort chat_gpt_prompt reversed
        chat_gpt_prompt.reverse()
        # Now add all values of chat_gpt_prompt to chat_gpt_prompt_original
        for item in chat_gpt_prompt:
            chat_gpt_prompt_original.append(item)

        # logger.info("chat_gpt_prompt_original: "+str(chat_gpt_prompt_original))

        return chat_gpt_prompt_original
    
    def log_message(self, chat_id: str, message_text: str):
        '''Logs a single message to a file, structured by chat_id.'''
        chat_log_path = os.path.join(self.data_dir, str(chat_id))
        Path(chat_log_path).mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        log_file_name = f"{timestamp}.json"
        with open(os.path.join(chat_log_path, log_file_name), 'w') as log_file:
            json.dump({"text": message_text}, log_file)

    def construct_prompt(self, chat_id: str):
        '''Constructs a chat history prompt from logged messages.'''
        chat_history = []
        chat_log_path = os.path.join(self.data_dir, str(chat_id))
        for log_file in sorted(os.listdir(chat_log_path)):
            with open(os.path.join(chat_log_path, log_file), 'r') as file:
                message_log = json.load(file)
                chat_history.append(HumanMessage(content=message_log['text']))
        return chat_history

    # The original llm_request function now refactored with Langchain's conversational agent
    # def llm_request(chat_id: str, message_text: str, user_session) -> str:
    def llm_request(self, user_session, message, system_content=None):
        chat_id = message['chat']['id']
        self.logger.info(f'llm_request: {chat_id}')

        # Construct the prompt from chat history
        prompt_messages = self.construct_prompt(chat_id=chat_id)

        message_text = message['text']

        # Append the current message to history for the response
        prompt_messages.append(HumanMessage(content=message_text))

        # Run the agent with the constructed history
        response = self.llm.run(input=prompt_messages, chat_history=prompt_messages, model=user_session['model'])

        # Log the new message
        self.log_message(chat_id=chat_id, message_text=message_text)

        # Assuming response is AIMessage object, extracting the text content
        response_text = response.content.strip() if isinstance(response, AIMessage) else "Sorry, I couldn't understand."

        return response_text

    """def llm_request_v0(self, user_session, message, system_content=None):
        chat_id = message['chat']['id']
        self.logger.info(f'llm_request: {chat_id}')
        
        prompt = self.read_latest_messages(user_session, message, system_content)

        llm_url = os.environ.get('LLM_URL', '')
        url = f'{llm_url}/request'
        request_data = {
            "api_key": os.environ.get('LLM_TOKEN', ''),
            "model": user_session['model'],
            "prompt": prompt
        }
        # Json dumps prompt
        prompt_dumped = json.dumps(prompt)
        tokens_count = self.token_counter(prompt_dumped, user_session['model']).json()['tokens']
        self.logger.info(f'tokens_count prognose: {tokens_count}')
        self.logger.info(f'url: {url}')
        self.logger.info(f'request_data: {request_data}')
        response = requests.post(url, json=request_data)
        self.logger.info(f'response: {str(response)}')
        response_json = json.loads(response.text)
        # Now, response_json is a string. Let's parse it into a json
        response_json = json.loads(response_json)

        bot_message = self.default_bot_message(
            message,
            response_json['choices'][0]['message']['content']
            )
        # Log message
        self.log_message(bot_message)
        # Remove left 11 signs: 'assistant: '
        if response_json['choices'][0]['message']['content'].startswith('assistant: '):
            response_text = response_json['choices'][0]['message']['content'][11:]
        else:
            response_text = response_json['choices'][0]['message']['content']

        # Remove 'Assistant: ' from response if it is there
        if response_text.startswith('Assistant: '):
            response_text = response_text[11:]

        # Return the response
        return response_text"""