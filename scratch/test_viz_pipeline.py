import os
import sys
import json
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'Backend')
load_dotenv('Backend/.env')

from ai.companion.gateway import MayaGateway
from ai.companion.schemas import CompanionChatRequest, CompanionChatMessage, CompanionContext

gateway = MayaGateway()

test_queries = [
    "Visualize how a stack works with push and pop operations.",
    "Visualize binary search on a sorted array.",
    "Visualize linked-list insertion.",
    "Visualize recursion with factorial(3).",
    "Visualize a binary tree with insertion of 5, 3, 7, 2, 4.",
    "Visualize" # Insufficient context test
]

for q in test_queries:
    print(f"\n========================================================")
    print(f"QUERY: '{q}'")
    print(f"========================================================")
    
    req = CompanionChatRequest(
        message=q,
        history=[],
        context=CompanionContext(
            student_id="test_student",
            student_name="Student",
            bot_name="Maya",
            active_workspace="dashboard"
        ),
        stream=True
    )
    
    stream = gateway.chat_stream(req)
    
    viz_event = None
    deltas = []
    done_event = None
    
    for event_str in stream:
        lines = event_str.strip().split("\n")
        ev_type = "message"
        data_str = ""
        for line in lines:
            if line.startswith("event:"):
                ev_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
        
        if ev_type == "delta" and data_str:
            d = json.loads(data_str)
            if d.get("text"):
                deltas.append(d["text"])
        elif ev_type == "visualization" and data_str:
            viz_event = json.loads(data_str)
        elif ev_type == "done" and data_str:
            done_event = json.loads(data_str)
    
    text = "".join(deltas)
    print(f"Text response sample: {text[:150].replace('\n', ' ')}...")
    if viz_event:
        print(f"SUCCESS: Visualization event emitted!")
        print(f"  viz_type: {viz_event.get('viz_type')}")
        print(f"  title: {viz_event.get('title')}")
        print(f"  steps count: {len(viz_event.get('steps', []))}")
        print(f"  initial_state: {viz_event.get('initial_state')}")
    else:
        print("No visualization event emitted.")
        if done_event and done_event.get("visualization"):
            print("Visualization was in done event:", done_event["visualization"]["viz_type"])
        else:
            print("Done event has no visualization.")
