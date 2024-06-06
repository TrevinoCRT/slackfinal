import asyncio
import threading
from flask import Flask
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from loguru import logger
from assistants import process_thread_with_assistant
import os


# Configure Loguru
logger.add(rotation="1 week", retention="1 month", level="DEBUG", format="{time} {level} {message}")
logger.debug("Loguru configured with file rotation and retention")

# Initialize Flask app
app = Flask(__name__)
logger.debug("Flask app initialized")

# Initialize Slack app with Socket Mode
slack_app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
logger.debug("Slack app initialized with token")
socket_mode_handler = SocketModeHandler(slack_app, os.environ["SLACK_APP_TOKEN"])
logger.debug("SocketModeHandler initialized with app token")

AUTHORIZED_USER_IDS = os.environ.get("AUTHORIZED_USER_IDS", "")
logger.debug(f"Authorized user IDs loaded: {AUTHORIZED_USER_IDS}")

# Define assistant IDs and their corresponding vectorstores
DRUMBEAT_ASSISTANT_DATA = {
    "Digital Operations & Item Optimization Drumbeat": {
        "assistant_id": "asst_bfeNzvue6C0HcuZW12zyOVN3",
        "vectorstore_id": "vs_HkmRIQj9IHz0UfLxXRtg5cPh"
    },
    "Cobrand Drumbeat": {
        "assistant_id": "asst_1MbUsEtQOlKEgHyZWe0B1qww",
        "vectorstore_id": "vs_eeyOxbl9t2PIlHZ7Qh14d9mU"
    },
    "Cohesive Infrastructure Drumbeat": {
        "assistant_id": "asst_qEvyuIDfNgHLXAw8pugOJJaM",
        "vectorstore_id": "vs_xmBo7YzGxSM4v83JXpE9w3uc"
    },
    "Data Center Transformation Drumbeat": {
        "assistant_id": "asst_Puw0dDhkbmif5J539YZ5QtWo",
        "vectorstore_id": "vs_EwsKoMBPy44rn8yZB5piKFSb"
    },
    "Price Value Drumbeat": {
        "assistant_id": "asst_cBmQeScCytEgcGZXNga48jTd",
        "vectorstore_id": "vs_29ir02A6qQRlQu6o60E5PE3T"
    },
    "Shared Services Drumbeat": {
        "assistant_id": "asst_SyHDBVmfGRyF7sphjIW4zb8m",
        "vectorstore_id": "vs_dLod268BpXU3U130zo3lJwc9"
    },
    "Stores Digital Marketing EPS Customer Service Drumbeat": {
        "assistant_id": "asst_SxHrs2fjUPDk2NJuvS6fJSyG",
        "vectorstore_id": "vs_eXBn7iBGBs9olJUfexXo3dOT"
    },
    "Supply Chain Merch Drumbeat": {
        "assistant_id": "asst_Jd3zI5eN8nizBexRqWtszb5Z",
        "vectorstore_id": "vs_9l1VMkTb1pjzEC2ldhSREU8B"
    },
    "Technical Project Management - Stores and Infra Drumbeat": {
        "assistant_id": "asst_jY7VZwwlBXX0uatzUsp5M7im",
        "vectorstore_id": "vs_Li0lfoy6vt9enbzOImxPPHsS"
    },
    "Test for Allocation Supply Team": {
        "assistant_id": "asst_qPZ55zXeulxiaLXyCJlHM0LD",
        "vectorstore_id": "vs_1d1MAdCRPQMM93uNqspijKJB"
    }
}
logger.debug("Assistant IDs and vectorstores defined")

# Default assistant ID (you can set this to one of the drumbeat assistant IDs)
assistant_id = DRUMBEAT_ASSISTANT_DATA["Test for Allocation Supply Team"]["assistant_id"]
logger.debug(f"Default assistant ID set to: {assistant_id}")

def is_authorized_user(user_id):
    authorized_ids = AUTHORIZED_USER_IDS.split(',')
    logger.debug(f"Checking if user ID {user_id} is authorized")
    return user_id in authorized_ids

@slack_app.message("")
def message_handler(message, say, ack):
    ack()
    user_id = message.get('user')

    if not is_authorized_user(user_id):
        logger.warning(f"Unauthorized message from user ID: {user_id}")
        return  # Simply return without processing the message

    logger.debug(f"Received message from user: {user_id}")
    user_query = message['text']
    from_user = message['user']
    thread_ts = message['ts']  # Get the timestamp of the user's message to use as thread_ts
    logger.debug(f"Authorized user {from_user} sent a query: {user_query}")

    def process_and_respond():
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        logger.debug("Event loop set for async processing.")
        async def async_process_and_respond():
            global assistant_id  # Access the global assistant_id
            response = await process_thread_with_assistant(user_query, assistant_id, from_user=from_user)
            if response:
                for text in response.get("text", []):
                    slack_app.client.chat_postMessage(
                        channel=message['channel'],
                        text=text,
                        mrkdwn=True,
                        thread_ts=thread_ts  # Post the response in the same thread
                    )
            else:
                say("Sorry, I couldn't process your request.", thread_ts=thread_ts)
            logger.info("Response processed and sent to user.")

        loop.run_until_complete(async_process_and_respond())

    threading.Thread(target=process_and_respond).start()
    logger.debug("Processing user query in a separate thread.")

@slack_app.action("select_drumbeat")
def handle_drumbeat_selection(ack, body, logger):
    global assistant_id  # Access the global assistant_id
    selected_drumbeat = body['actions'][0]['selected_option']['value']
    assistant_data = DRUMBEAT_ASSISTANT_DATA.get(selected_drumbeat)
    if assistant_data:
        assistant_id = assistant_data["assistant_id"]
    else:
        assistant_id = os.environ.get('ASSISTANT_ID')
    logger.info(f"Selected drumbeat: {selected_drumbeat}, Assistant ID: {assistant_id}")
    ack()

@slack_app.event("app_home_opened")
def app_home_opened(client, event, logger):
    try:
        client.views_publish(
            user_id=event["user"],
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Welcome to the AI Assistant Dashboard!*"
                        }
                    },
                    {"type": "divider"},
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Select a Drumbeat to interact with:"
                        },
                        "accessory": {
                            "type": "static_select",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Select a Drumbeat",
                                "emoji": True
                            },
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": drumbeat_name,
                                        "emoji": True
                                    },
                                    "value": drumbeat_name
                                } for drumbeat_name in DRUMBEAT_ASSISTANT_DATA
                            ],
                            "action_id": "select_drumbeat"
                        }
                    },
                    {"type": "divider"},
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Here are some example prompts to get you started:\n• What is the latest information on [topic]?\n• Can you provide a summary of [document/topic]?\n• What are the key takeaways from [meeting/event]?"
                        }
                    }
                ]
            }
        )
    except Exception as e:
        logger.error(f"Error publishing home tab: {e}")

def process_message(event):
    user_id = event['user']
    text = event['text']
    channel = event['channel']
    # Assuming process_thread_with_assistant is adapted to handle these parameters
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(process_thread_with_assistant(text, os.getenv('ASSISTANT_ID'), from_user=user_id))
    if response:
        for text in response.get("text", []):
            slack_app.client.chat_postMessage(
                channel=channel,
                text=text,
                mrkdwn=True
            )
    loop.close()

# Start the Flask app
if __name__ == "__main__":
    socket_mode_handler.start()
