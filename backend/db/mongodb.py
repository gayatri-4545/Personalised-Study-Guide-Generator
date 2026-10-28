"""
MongoDB connection (async, via motor) and collection accessors.
Collections match the spec (section 5 / section 7):
    users, study_requests, generated_guides, request_history,
    agent_execution_history, document_metadata,
    user_progress, quiz_attempts, topic_mastery_summary
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config.settings import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def connect():
    global _client, _db
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGODB_URI)
        _db = _client[settings.MONGODB_DB_NAME]
    return _db


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        return connect()
    return _db


def close():
    global _client
    if _client is not None:
        _client.close()
        _client = None


# --- Collection shortcuts -------------------------------------------------
def users():
    return get_db()["users"]


def study_requests():
    return get_db()["study_requests"]


def generated_guides():
    return get_db()["generated_guides"]


def request_history():
    return get_db()["request_history"]


def agent_execution_history():
    return get_db()["agent_execution_history"]


def document_metadata():
    return get_db()["document_metadata"]


def user_progress():
    return get_db()["user_progress"]


def quiz_attempts():
    return get_db()["quiz_attempts"]


def topic_mastery_summary():
    return get_db()["topic_mastery_summary"]
