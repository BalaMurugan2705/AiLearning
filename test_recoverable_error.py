# Import JSON to inspect the error returned by the failing tool.
import json

# SimpleNamespace lets us create lightweight mock LLM responses.
from types import SimpleNamespace

# Import the agent loop and its budget configuration.
from agent.loop import run_agent
from agent.budgets import Budget


# Simulate an MCP tool that fails with a recoverable runtime error.
def failing_tool(package_name: str):
    raise RuntimeError("Simulated package registry timeout")


# Register the failing tool under the name expected by the LLM.
tool_functions = {
    "get_package_api_spec": failing_tool,
}


# Define the tool schema so the mock response matches the agent's interface.
tool_schemas = [
    {
        "type": "function",
        "function": {
            "name": "get_package_api_spec",
            "description": "Retrieve a package API specification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {"type": "string"},
                },
                "required": ["package_name"],
            },
        },
    }
]


# Build a fake LLM tool call that invokes the registered failing tool.
tool_call = SimpleNamespace(
    id="call_test_001",
    function=SimpleNamespace(
        name="get_package_api_spec",
        arguments=json.dumps({"package_name": "example-package"}),
    ),
)


# Create the first response: the LLM requests the tool.
first_response = SimpleNamespace(
    usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    choices=[
        SimpleNamespace(
            message=SimpleNamespace(
                content=None,
                tool_calls=[tool_call],
            )
        )
    ],
)


# Create the second response: the LLM recovers and returns a final answer.
second_response = SimpleNamespace(
    usage=SimpleNamespace(prompt_tokens=15, completion_tokens=10),
    choices=[
        SimpleNamespace(
            message=SimpleNamespace(
                content="The package registry timed out. Please retry.",
                tool_calls=None,
            )
        )
    ],
)


# Return the two mock responses in sequence, without calling a real LLM.
class MockCompletions:
    def __init__(self):
        self.responses = [first_response, second_response]
        self.call_count = 0
        self.requests = []

    def create(self, **kwargs):
        # Capture the conversation so the test can inspect the tool error.
        self.requests.append(kwargs)

        # Return the next simulated LLM response.
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


# Match the nested client.chat.completions.create interface used by run_agent.
mock_client = SimpleNamespace(
    chat=SimpleNamespace(
        completions=MockCompletions()
    )
)


# Provide generous limits so the test exercises error recovery, not budgets.
budget = Budget(
    max_iterations=5,
    max_tokens=10000,
    max_cost_usd=1.0,
    max_wall_seconds=60,
)


# Run the agent with the mock client and the simulated failing tool.
result = run_agent(
    question="Get the API specification for example-package.",
    budget=budget,
    client=mock_client,
    tool_schemas=tool_schemas,
    tool_functions=tool_functions,
)


# Confirm the agent recovered and returned the mock final answer.
assert result.answer == "The package registry timed out. Please retry."

# Confirm the agent made two LLM calls: tool selection and final response.
assert mock_client.chat.completions.call_count == 2

# Inspect the second LLM request, which should contain the failed tool result.
second_request_messages = mock_client.chat.completions.requests[1]["messages"]

# Locate the tool message containing the simulated timeout.
tool_messages = [
    message
    for message in second_request_messages
    if message["role"] == "tool"
]

# Verify that the tool error was passed back to the LLM as JSON.
assert len(tool_messages) == 1

error_result = json.loads(tool_messages[0]["content"])

assert error_result["error"] == "Simulated package registry timeout"
assert error_result["tool"] == "get_package_api_spec"

# Print confirmation only after all assertions pass.
print("PASS: Tool exception was returned to the LLM and the agent recovered.")
print(f"Final answer: {result.answer}")