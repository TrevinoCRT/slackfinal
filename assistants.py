import asyncio
import json
import os
from openai import AsyncOpenAI
from loguru import logger
from file_utils import replace_file_ids_with_urls
import re


# Global variables
global_thread_id = None

api_key = os.environ.get("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=api_key)

def format_for_slack(text):
    """Formats text for Slack, replacing Markdown elements for better compatibility.

    Args:
        text (str): The input text with Markdown formatting.

    Returns:
        str: The formatted text with Slack-compatible formatting.
    """
    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    # Italics
    text = re.sub(r'\*(.*?)\*', r'_\1_', text)
    # Strikethrough (No Slack equivalent - removing)
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    # Inline Code (No Slack equivalent - removing)
    text = re.sub(r'`(.*?)`', r'\1', text)
    # Blockquote 
    text = re.sub(r'^> (.*)', r'\n>\1', text, flags=re.MULTILINE)
    # Code Block (No Slack equivalent - removing backticks)
    text = re.sub(r'```(.*?)```', r'\1', text, flags=re.DOTALL)
    # Ordered List
    text = re.sub(r'(\d+)\. ', r'\1. \n', text)  # Add newline after each list item
    # Bulleted List
    text = re.sub(r'^\* ', r'• ', text, flags=re.MULTILINE)  # Replace asterisk with bullet point
    # Headings
    text = re.sub(r'^# (.*?)\n', r'*\1*\n', text)  # H1 to bold
    text = re.sub(r'^## (.*?)\n', r'_\1_\n', text)  # H2 to italic
    text = re.sub(r'### (.*?)\n', r'*\1*\n', text)  # H3 to bold
    text = re.sub(r'#### (.*?)\n', r'_\1_\n', text)  # H4 to italic

    return text

async def execute_function(function_name, arguments, from_user):
    # Implement your function execution logic here
    # For now, return a dummy response
    return {"status": "error", "message": "Function not recognized"}

async def process_tool_call(tool_call, from_user):
    function_name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments)
    function_output = await execute_function(function_name, arguments, from_user)
    function_output_str = json.dumps(function_output)
    return {
        "tool_call_id": tool_call.id,
        "output": function_output_str
    }

async def process_thread_with_assistant(query, assistant_id, model="gpt-4o", from_user=None):
    global global_thread_id
    response_texts = []
    response_files = []
    in_memory_files = []
    try:
        if not global_thread_id:
            logger.debug("Creating a new thread for the user query...")
            thread = await client.beta.threads.create()
            global_thread_id = thread.id
            logger.debug(f"New thread created with ID: {global_thread_id}")
        
        logger.debug(f"Adding the user query as a message to the thread with ID: {global_thread_id}, query: {query}")
        await client.beta.threads.messages.create(
            thread_id=global_thread_id,
            role="user",
            content=query
        )
        logger.debug("User query added to the thread.")

        logger.debug(f"Creating a run to process the thread with the assistant ID: {assistant_id}, model: {model}")
        run = await client.beta.threads.runs.create(
            thread_id=global_thread_id,
            assistant_id=assistant_id,
            model=model
        )
        logger.debug(f"Run created with ID: {run.id}")

        while True:
            logger.debug(f"Checking the status of the run with ID: {run.id}")
            run_status = await client.beta.threads.runs.retrieve(
                thread_id=global_thread_id,
                run_id=run.id
            )
            logger.debug(f"Current status of the run: {run_status.status}")

            if run_status.status == "requires_action":
                logger.debug("Run requires action. Executing specified functions in parallel...")
                tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                logger.debug(f"Tool calls to process: {tool_calls}")
                tasks = [process_tool_call(tool_call, from_user) for tool_call in tool_calls]
                tool_outputs = await asyncio.gather(*tasks)
                logger.debug(f"Tool outputs: {tool_outputs}")

                logger.debug(f"Submitting tool outputs for run ID: {run.id}")
                await client.beta.threads.runs.submit_tool_outputs(
                    thread_id=global_thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )
                logger.debug("Tool outputs submitted.")

            elif run_status.status in ["completed", "failed", "cancelled"]:
                logger.debug(f"Fetching the latest message added by the assistant for thread ID: {global_thread_id}")
                messages_response = await client.beta.threads.messages.list(
                    thread_id=global_thread_id,
                    order="desc"
                )
                messages = messages_response.data  # Access the data attribute directly

                # Iterate through messages
                latest_assistant_message = next((message for message in messages if message.role == "assistant"), None)

                logger.debug(f"Latest assistant message: {latest_assistant_message}")

                if latest_assistant_message:
                    for content in latest_assistant_message.content:
                        logger.debug(f"Processing content: {content}")
                        if content.type == "text":
                            text_value = content.text.value
                            logger.debug(f"Original text value: {text_value}")
                            text_value = await replace_file_ids_with_urls(text_value)  # Use await for async function
                            logger.debug(f"Text value after replacing file IDs with URLs: {text_value}")

                            # Format the text for Slack
                            text_value = format_for_slack(text_value)
                            logger.debug(f"Text value after Slack formatting: {text_value}")

                            for annotation in content.text.annotations:
                                logger.debug(f"Processing annotation: {annotation}")
                                if annotation.type == "file_citation":
                                    cited_file = await client.files.retrieve(annotation.file_citation.file_id)
                                    logger.debug(f"Cited file: {cited_file}")
                                    citation_text = f"[Cited from {cited_file.filename}]"
                                    text_value = text_value.replace(annotation.text, citation_text)
                                    logger.debug(f"Text value after replacing file citation: {text_value}")
                                elif annotation.type == "file_path":
                                    file_info = await client.files.retrieve(annotation.file_path.file_id)
                                    logger.debug(f"File info: {file_info}")
                                    download_link = f"<https://platform.openai.com/files/{file_info.id}|Download {file_info.filename}>"
                                    text_value = text_value.replace(annotation.text, download_link)
                                    logger.debug(f"Text value after replacing file path: {text_value}")
                            response_texts.append(text_value)
                            logger.debug(f"Appended text value to response_texts: {text_value}")
                        elif content.type == "file":
                            file_id = content.file.file_id
                            file_mime_type = content.file.mime_type
                            logger.debug(f"File ID: {file_id}, MIME type: {file_mime_type}")
                            response_files.append((file_id, file_mime_type))

                    for file_id, mime_type in response_files:
                        try:
                            logger.debug(f"Retrieving content for file ID: {file_id} with MIME type: {mime_type}")
                            file_response = await client.files.content(file_id)
                            file_content = file_response.content if hasattr(file_response, 'content') else file_response
                            logger.debug(f"File content retrieved: {file_content}")
                            extensions = {
                                "text/x-c": ".c", "text/x-csharp": ".cs", "text/x-c++": ".cpp",
                                "application/msword": ".doc", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                                "text/html": ".html", "text/x-java": ".java", "application/json": ".json",
                                "text/markdown": ".md", "application/pdf": ".pdf", "text/x-php": ".php",
                                "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
                                "text/x-python": ".py", "text/x-script.python": ".py", "text/x-ruby": ".rb",
                                "text/x-tex": ".tex", "text/plain": ".txt", "text/css": ".css",
                                "text/javascript": ".js", "application/x-sh": ".sh", "application/typescript": ".ts",
                                "application/csv": ".csv", "image/jpeg": ".jpeg", "image/gif": ".gif",
                                "image/png": ".png", "application/x-tar": ".tar",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                                "application/xml": "text/xml", "application/zip": ".zip"
                            }
                            file_extension = extensions.get(mime_type, ".bin")
                            logger.debug(f"File extension determined: {file_extension}")

                            local_file_path = f"./downloaded_file_{file_id}{file_extension}"
                            with open(local_file_path, "wb") as local_file:
                                local_file.write(file_content)
                            logger.debug(f"File saved locally at {local_file_path}")

                        except Exception as e:
                            logger.error(f"Failed to retrieve content for file ID: {file_id}. Error: {e}")

                break
            await asyncio.sleep(1)

        logger.debug(f"Returning response texts: {response_texts} and in-memory files: {in_memory_files}")
        return {"text": response_texts, "in_memory_files": in_memory_files}

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return {"text": [], "in_memory_files": []}