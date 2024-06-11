import asyncio
import threading
from flask import Flask
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from loguru import logger
from assistants import process_thread_with_assistant
import os
from dotenv import load_dotenv

load_dotenv()

# Configure Loguru
logger.add("app.log", rotation="500 MB", retention="10 days", level="DEBUG")
logger.debug("Loguru configured with file rotation and retention")

# Initialize Slack app with Socket Mode
slack_app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
logger.debug("Slack app initialized with token")

socket_mode_handler = SocketModeHandler(slack_app, os.environ["SLACK_APP_TOKEN"])
logger.debug("SocketModeHandler initialized with app token")

AUTHORIZED_USER_IDS = os.environ.get("AUTHORIZED_USER_IDS", "").split(',')
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

# User Sessions: Dictionary to store user-specific thread IDs and selected assistant
user_sessions = {}
logger.debug("User session dictionary initialized")

def is_authorized_user(user_id):
    logger.debug(f"Checking if user ID {user_id} is authorized")
    return user_id in AUTHORIZED_USER_IDS

@slack_app.message("")
def message_handler(message, say, ack):
    ack()
    user_id = message.get('user')

    if not is_authorized_user(user_id):
        logger.warning(f"Unauthorized message from user ID: {user_id}")
        say(f"Sorry <@{user_id}>, you are not authorized to use this bot.")
        return  # Simply return without processing the message

    logger.debug(f"Received message from authorized user: {user_id}")
    user_query = message['text']
    thread_ts = message['ts']
    channel = message['channel']

    # Get or create a thread ID for the user
    if user_id not in user_sessions:
        user_sessions[user_id] = {"thread_id": None, "assistant_id": os.environ.get('ASSISTANT_ID')}
    thread_id = user_sessions[user_id]["thread_id"]

    def process_and_respond():
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        logger.debug("Event loop set for async processing.")

        async def async_process_and_respond():
            assistant_id = user_sessions[user_id]["assistant_id"]
            response = await process_thread_with_assistant(
                user_query, assistant_id, from_user=user_id, thread_id=thread_id
            )
            logger.debug(f"Response from assistant: {response}")

            if response:
                user_sessions[user_id]["thread_id"] = response.get("thread_id")
                for text in response.get("text", []):
                    slack_app.client.chat_postMessage(
                        channel=channel,
                        text=text,
                        mrkdwn=True,
                        thread_ts=thread_ts
                    )
            else:
                say("Sorry, I couldn't process your request.", thread_ts=thread_ts)
            logger.info("Response processed and sent to user.")

        loop.run_until_complete(async_process_and_respond())

    threading.Thread(target=process_and_respond).start()
    logger.debug("Processing user query in a separate thread.")

@slack_app.action("select_drumbeat")
def handle_drumbeat_selection(ack, body, logger):
    user_id = body['user']['id']
    selected_drumbeat = body['actions'][0]['selected_option']['value']
    assistant_data = DRUMBEAT_ASSISTANT_DATA.get(selected_drumbeat)
    if assistant_data:
        user_sessions[user_id]["assistant_id"] = assistant_data["assistant_id"]
        logger.info(f"User {user_id} selected drumbeat: {selected_drumbeat}, Assistant ID: {assistant_data['assistant_id']}")
    else:
        logger.error(f"Invalid drumbeat selection: {selected_drumbeat}")
    ack()

@slack_app.event("app_home_opened")
def app_home_opened(client, event, logger):
    user_id = event["user"]
    if is_authorized_user(user_id):
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
    else:
        client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Sorry, you are not authorized to use this app."
                        }
                    }
                ]
            }
        )


# Start the Flask app
if __name__ == "__main__":
    socket_mode_handler.start()