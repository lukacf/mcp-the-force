#!/usr/bin/env python3
"""
Test synthetic data for project memory system.
Creates two vector stores with conversations and commits, then tests retrieval.
"""

import asyncio
import json
import os
import random
from datetime import datetime, timedelta

from mcp_second_brain.utils.vector_store import get_client


# Synthetic data generation
def generate_synthetic_data():
    """Generate synthetic conversation and commit data"""

    # Simulate a week of development
    base_time = datetime(2024, 1, 15, 9, 0, 0)

    conversations = []
    commits = []

    # Branch names
    branches = ["main", "feature/auth", "feature/api", "bugfix/timeout"]

    # Common topics
    topics = {
        "auth": ["JWT", "OAuth", "authentication", "login", "security"],
        "api": ["REST", "GraphQL", "endpoints", "validation", "schema"],
        "timeout": ["performance", "async", "connection", "retry", "error handling"],
        "database": ["PostgreSQL", "migrations", "indexes", "queries", "optimization"],
    }

    # Generate development timeline
    current_time = base_time
    commit_shas = ["abc123"]  # Starting commit

    for day in range(7):
        branch = random.choice(branches)
        topic = random.choice(list(topics.keys()))

        # Morning: Have a conversation with AI assistant
        conv_time = current_time + timedelta(hours=random.randint(0, 4))
        session_id = f"session-{day}-{topic}"

        conversation = {
            "content": f"""
## Session: {session_id}
Date: {conv_time.isoformat()}

User asked about implementing {topic} features.

Assistant (o3) provided detailed analysis:
- Recommended using {random.choice(topics[topic])} pattern
- Discussed trade-offs between different approaches
- Suggested specific implementation steps
- Warned about potential {random.choice(['security', 'performance', 'maintainability'])} issues

Key decisions made:
1. Use {random.choice(topics[topic])} for better {random.choice(['scalability', 'reliability', 'simplicity'])}
2. Implement comprehensive error handling
3. Add proper logging and monitoring
""",
            "metadata": {
                "type": "conversation",
                "session_id": session_id,
                "branch": branch,
                "prev_commit_sha": commit_shas[-1],
                "timestamp": int(conv_time.timestamp()),
                "tool": random.choice(["chat_with_o3", "chat_with_gemini25_pro"]),
                "topic": topic,
            },
        }
        conversations.append(conversation)

        # Afternoon: Make commits based on conversation
        commit_time = conv_time + timedelta(hours=random.randint(4, 8))
        new_sha = f"sha{day}{random.randint(1000, 9999)}"

        commit = {
            "content": f"""
## Commit: {new_sha}
Date: {commit_time.isoformat()}
Branch: {branch}

Implemented {topic} improvements based on AI consultation.

Changes:
- Updated {topic}.py with new {random.choice(topics[topic])} implementation
- Added comprehensive test coverage
- Refactored existing code for better {random.choice(['performance', 'readability', 'maintainability'])}
- Fixed edge cases identified during code review

Files changed:
- src/{topic}.py
- tests/test_{topic}.py
- docs/{topic}.md
""",
            "metadata": {
                "type": "commit",
                "commit_sha": new_sha,
                "parent_sha": commit_shas[-1],
                "branch": branch,
                "timestamp": int(commit_time.timestamp()),
                "files_changed": [f"src/{topic}.py", f"tests/test_{topic}.py"],
                "session_id": session_id,  # Link to conversation
            },
        }
        commits.append(commit)
        commit_shas.append(new_sha)

        # Sometimes have conversations without commits
        if random.random() > 0.7:
            orphan_conv = {
                "content": f"""
## Session: orphan-{day}
Quick consultation about {random.choice(list(topics.keys()))} optimization.
No code changes made yet - still researching options.
""",
                "metadata": {
                    "type": "conversation",
                    "session_id": f"orphan-{day}",
                    "branch": branch,
                    "prev_commit_sha": commit_shas[-1],
                    "timestamp": int((conv_time + timedelta(hours=2)).timestamp()),
                },
            }
            conversations.append(orphan_conv)

        current_time += timedelta(days=1)

    return conversations, commits


async def create_test_stores():
    """Create and populate test vector stores"""
    client = get_client()

    # Create stores
    conv_store = client.vector_stores.create(name="test-conversations")
    commit_store = client.vector_stores.create(name="test-commits")

    print(f"Created conversation store: {conv_store.id}")
    print(f"Created commit store: {commit_store.id}")

    # Generate data
    conversations, commits = generate_synthetic_data()

    print(f"\nGenerated {len(conversations)} conversations and {len(commits)} commits")

    # Upload conversations
    conv_files = []
    for i, conv in enumerate(conversations):
        filename = f"conv_{i}_{conv['metadata']['session_id']}.json"
        with open(f"/tmp/{filename}", "w") as f:
            json.dump(conv, f, indent=2)
        conv_files.append(open(f"/tmp/{filename}", "rb"))

    if conv_files:
        client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=conv_store.id, files=conv_files
        )
        print(f"Uploaded {len(conv_files)} conversations")

    # Upload commits
    commit_files = []
    for i, commit in enumerate(commits):
        filename = f"commit_{i}_{commit['metadata']['commit_sha']}.json"
        with open(f"/tmp/{filename}", "w") as f:
            json.dump(commit, f, indent=2)
        commit_files.append(open(f"/tmp/{filename}", "rb"))

    if commit_files:
        client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=commit_store.id, files=commit_files
        )
        print(f"Uploaded {len(commit_files)} commits")

    # Cleanup
    for f in conv_files + commit_files:
        f.close()

    return conv_store.id, commit_store.id


async def test_model_reasoning(conv_store_id: str, commit_store_id: str):
    """Test how different models connect conversations to commits"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI()

    # Test query that requires connecting conversation to commit
    test_query = "What was the reasoning behind the authentication implementation and what specific changes were made?"

    print("\n" + "=" * 60)
    print("TESTING MODEL REASONING CAPABILITIES")
    print("=" * 60)
    print(f"Query: {test_query}")
    print("=" * 60)

    # Test both o3 and gpt-4.1
    models = ["o3", "gpt-4.1"]

    for model in models:
        print(f"\n\nTesting with {model}")
        print("-" * 40)

        try:
            response = await client.responses.create(
                model=model,
                input=test_query,
                tools=[
                    {
                        "type": "file_search",
                        "vector_store_ids": [conv_store_id, commit_store_id],
                        "max_num_results": 10,  # Get more results to test connection ability
                    }
                ],
            )

            # Extract the actual response
            message_output = None

            for output in response.output:
                if output.type == "message":
                    message_output = output

            if message_output:
                print(f"\n{model.upper()} Response:")
                print(message_output.content[0].text)

                # Count citations
                citations = (
                    message_output.content[0].annotations
                    if hasattr(message_output.content[0], "annotations")
                    else []
                )
                print(f"\nNumber of citations: {len(citations)}")

                # Analyze if model connected conversation to commit
                response_text = message_output.content[0].text.lower()
                reasoning_mentioned = any(
                    word in response_text
                    for word in [
                        "reasoning",
                        "recommended",
                        "consultation",
                        "discussion",
                    ]
                )
                implementation_mentioned = any(
                    word in response_text
                    for word in ["implemented", "changes", "commit", "updated"]
                )

                print(
                    f"Mentioned reasoning/consultation: {'Yes' if reasoning_mentioned else 'No'}"
                )
                print(
                    f"Mentioned implementation/changes: {'Yes' if implementation_mentioned else 'No'}"
                )
                print(
                    f"Successfully connected both: {'Yes' if reasoning_mentioned and implementation_mentioned else 'No'}"
                )

        except Exception as e:
            print(f"Error with {model}: {e}")


async def test_retrieval(conv_store_id: str, commit_store_id: str):
    """Test various retrieval scenarios"""
    client = get_client()

    test_queries = [
        "How did we implement authentication?",
        "What were the performance improvements?",
        "Show me the timeout bug fix",
        "What did o3 recommend for the API design?",
        "What changes were made to the database?",
    ]

    print("\n" + "=" * 60)
    print("TESTING BASIC RETRIEVAL")
    print("=" * 60)

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 40)

        # Search both stores
        conv_results = client.vector_stores.search(
            vector_store_id=conv_store_id, query=query, max_num_results=5
        )

        commit_results = client.vector_stores.search(
            vector_store_id=commit_store_id, query=query, max_num_results=5
        )

        print(
            f"Found {len(conv_results.data)} conversations, {len(commit_results.data)} commits"
        )

        # Look for metadata connections
        connections = []
        for conv in conv_results.data:
            conv_data = json.loads(conv.content[0].text)
            conv_meta = conv_data.get("metadata", {})

            for commit in commit_results.data:
                commit_data = json.loads(commit.content[0].text)
                commit_meta = commit_data.get("metadata", {})

                # Check various connection types
                if conv_meta.get("session_id") == commit_meta.get(
                    "session_id"
                ) or conv_meta.get("prev_commit_sha") == commit_meta.get("parent_sha"):
                    connections.append(
                        {
                            "conversation": conv_meta.get("session_id"),
                            "commit": commit_meta.get("commit_sha"),
                            "match_type": "direct"
                            if conv_meta.get("session_id")
                            == commit_meta.get("session_id")
                            else "sha_based",
                        }
                    )

        if connections:
            print(f"Found {len(connections)} connected pairs:")
            for conn in connections:
                print(
                    f"  - {conn['conversation']} → {conn['commit']} ({conn['match_type']})"
                )
        else:
            print("No direct connections found via metadata")

        # Show top results
        if conv_results.data:
            top_conv = json.loads(conv_results.data[0].content[0].text)
            print(f"\nTop conversation (score: {conv_results.data[0].score:.3f}):")
            print(f"  Session: {top_conv['metadata'].get('session_id')}")
            print(f"  Branch: {top_conv['metadata'].get('branch')}")
            print(f"  Topic: {top_conv['metadata'].get('topic', 'N/A')}")

        if commit_results.data:
            top_commit = json.loads(commit_results.data[0].content[0].text)
            print(f"\nTop commit (score: {commit_results.data[0].score:.3f}):")
            print(f"  SHA: {top_commit['metadata'].get('commit_sha')}")
            print(f"  Branch: {top_commit['metadata'].get('branch')}")
            print(f"  Session: {top_commit['metadata'].get('session_id', 'N/A')}")


async def main():
    """Run the test"""
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        return

    # Create and populate stores
    conv_store_id, commit_store_id = await create_test_stores()

    # Wait a bit for indexing
    print("\nWaiting for indexing...")
    await asyncio.sleep(5)

    # Test basic retrieval
    await test_retrieval(conv_store_id, commit_store_id)

    # Test model reasoning
    await test_model_reasoning(conv_store_id, commit_store_id)

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print(f"\nConversation store: {conv_store_id}")
    print(f"Commit store: {commit_store_id}")
    print("\nTo clean up, delete these stores manually via the OpenAI API")


if __name__ == "__main__":
    asyncio.run(main())
