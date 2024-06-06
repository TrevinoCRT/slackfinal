import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
from loguru import logger

logger.debug("Loading environment variables from .env file")
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
logger.debug(f"Retrieved API key from environment: {api_key}")

client = AsyncOpenAI(api_key=api_key)
logger.debug("Initialized OpenAI client")

async def list_files():
    logger.debug("Listing files from OpenAI")
    response = await client.files.list()
    logger.debug(f"Received response from OpenAI: {response}")
    return response.data # Access the 'data' attribute

async def retrieve_file(file_id):
    logger.debug(f"Retrieving file with ID: {file_id}")
    response = await client.files.retrieve(file_id)
    logger.debug(f"Received file data: {response}")
    return response

async def get_file_url(file_id):
    logger.debug(f"Getting URL for file ID: {file_id}")
    file_info = await retrieve_file(file_id)
    file_url = f"https://platform.openai.com/files/{file_info.id}"
    logger.debug(f"Constructed file URL: {file_url}")
    return file_url

async def replace_file_ids_with_urls(text):
    logger.debug(f"Replacing file IDs with URLs in text: {text}")
    files = await list_files()  # await the async function call
    for file in files: 
        file_id = file.id
        logger.debug(f"Processing file ID: {file_id}")
        file_url = await get_file_url(file_id)  # await the async function call
        logger.debug(f"Replacing file ID {file_id} with URL {file_url}")
        text = text.replace(file_id, file_url)
    logger.debug(f"Final text after replacements: {text}")
    return text