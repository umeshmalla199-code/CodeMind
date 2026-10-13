from typing import Optional, Dict, Any
from ai.companion.schemas import VisualizationSpec, VisualizationStep

def get_visualization_for_topic(topic: str, context_details: Optional[Dict[str, Any]] = None) -> Optional[VisualizationSpec]:
    t_lower = (topic or "").lower()

    # 1. STACK
    if "stack" in t_lower:
        return VisualizationSpec(
            viz_type="stack",
            title="Stack LIFO Container (Push & Pop)",
            initial_state=[15, 28],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="push",
                    value=42,
                    pointer="TOP=index 2",
                    highlight_indices=[2],
                    explanation="Push element 42 onto the top of the stack. TOP pointer advances to index 2."
                ),
                VisualizationStep(
                    step_number=2,
                    action="push",
                    value=99,
                    pointer="TOP=index 3",
                    highlight_indices=[3],
                    explanation="Push element 99 onto the top of the stack. Stack depth is now 4."
                ),
                VisualizationStep(
                    step_number=3,
                    action="pop",
                    value=99,
                    pointer="TOP=index 2",
                    highlight_indices=[2],
                    explanation="Pop top element 99. Top reverts to index 2 (value 42)."
                )
            ]
        )

    # 2. CIRCULAR QUEUE
    elif "circular" in t_lower or "ring buffer" in t_lower or "circular queue" in t_lower:
        return VisualizationSpec(
            viz_type="circular_queue",
            title="Circular Queue Ring Buffer (Modulo Arithmetic)",
            initial_state=[10, 20, 30, None, None],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="enqueue",
                    value=40,
                    pointer="FRONT=0, REAR=3",
                    highlight_indices=[3],
                    explanation="Enqueue 40 into slot 3. Formula: (REAR + 1) % 5 = 3."
                ),
                VisualizationStep(
                    step_number=2,
                    action="dequeue",
                    value=10,
                    pointer="FRONT=1, REAR=3",
                    highlight_indices=[0],
                    explanation="Dequeue element 10 from FRONT (slot 0). FRONT advances: (0 + 1) % 5 = 1."
                ),
                VisualizationStep(
                    step_number=3,
                    action="enqueue",
                    value=50,
                    pointer="FRONT=1, REAR=4",
                    highlight_indices=[4],
                    explanation="Enqueue 50 into slot 4. Buffer occupancy is 4/5."
                ),
                VisualizationStep(
                    step_number=4,
                    action="enqueue",
                    value=60,
                    pointer="FRONT=1, REAR=0 (Wrapped)",
                    highlight_indices=[0],
                    explanation="Wrap-around enqueue! (4 + 1) % 5 = 0. Element 60 wraps into slot 0!"
                )
            ]
        )

    # 3. QUEUE
    elif "queue" in t_lower:
        return VisualizationSpec(
            viz_type="queue",
            title="Queue FIFO Conduit (Enqueue & Dequeue)",
            initial_state=[10, 20, 30],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="enqueue",
                    value=40,
                    pointer="REAR=index 3, FRONT=index 0",
                    highlight_indices=[3],
                    explanation="Enqueue 40 at the rear. REAR pointer advances to index 3."
                ),
                VisualizationStep(
                    step_number=2,
                    action="enqueue",
                    value=50,
                    pointer="REAR=index 4, FRONT=index 0",
                    highlight_indices=[4],
                    explanation="Enqueue 50 at the rear. Queue now contains 5 elements."
                ),
                VisualizationStep(
                    step_number=3,
                    action="dequeue",
                    value=10,
                    pointer="FRONT=index 1, REAR=index 4",
                    highlight_indices=[0],
                    explanation="Dequeue 10 from the front. FRONT pointer advances to index 1 (value 20)."
                )
            ]
        )

    # 4. FLOWCHART / GENERIC ALGORITHM
    elif "flowchart" in t_lower or "prime" in t_lower or "algorithm" in t_lower or "state" in t_lower:
        return VisualizationSpec(
            viz_type="flowchart",
            title="Algorithm Flowchart & State Execution (Prime Number Check)",
            initial_state=["Start: n=29", "Check n <= 1", "Loop i=2..sqrt(n)", "Divisibility Test", "Output Result"],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="decision",
                    value="n = 29",
                    pointer="Step 1: Input Check",
                    highlight_indices=[0, 1],
                    explanation="Start with n = 29. Check base condition: is n <= 1? False, proceed to divisor test."
                ),
                VisualizationStep(
                    step_number=2,
                    action="loop",
                    value="i = 2",
                    pointer="Step 2: Check 29 % 2",
                    highlight_indices=[2, 3],
                    explanation="Test divisor i=2: 29 % 2 == 1 (non-zero remainder). Increment i."
                ),
                VisualizationStep(
                    step_number=3,
                    action="loop",
                    value="i = 3",
                    pointer="Step 3: Check 29 % 3",
                    highlight_indices=[2, 3],
                    explanation="Test divisor i=3: 29 % 3 == 2 (non-zero remainder). Increment i."
                ),
                VisualizationStep(
                    step_number=4,
                    action="loop",
                    value="i = 5",
                    pointer="Step 4: Check 29 % 5",
                    highlight_indices=[2, 3],
                    explanation="Test divisor i=5: 29 % 5 == 4. Note 5*5 = 25 <= 29; next candidate 6*6 = 36 > 29."
                ),
                VisualizationStep(
                    step_number=5,
                    action="decision",
                    value="Result: Prime",
                    pointer="Step 5: Termination",
                    highlight_indices=[4],
                    explanation="Divisor search limit (sqrt(29) ≈ 5.38) reached without zero remainder. Conclude: 29 is Prime!"
                )
            ]
        )

    # 3. LINKED LIST
    elif "linked" in t_lower or "list" in t_lower or "node" in t_lower:
        return VisualizationSpec(
            viz_type="linked_list",
            title="Singly Linked List: Node Traversal & Insertion",
            initial_state=[
                {"val": 12, "next": "Node 2"},
                {"val": 24, "next": "Node 3"},
                {"val": 48, "next": "NULL"}
            ],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="traverse",
                    pointer="HEAD -> Node 1",
                    highlight_indices=[0],
                    explanation="Start at HEAD (Node 1, value 12). Next points to Node 2."
                ),
                VisualizationStep(
                    step_number=2,
                    action="traverse",
                    pointer="curr -> Node 2",
                    highlight_indices=[1],
                    explanation="Traverse pointer: curr = curr.next (Node 2, value 24). Found insertion point."
                ),
                VisualizationStep(
                    step_number=3,
                    action="insert",
                    value=36,
                    pointer="New Node(36)",
                    highlight_indices=[1, 2],
                    explanation="Insert New Node(36): set new_node.next = Node 3, then Node 2.next = new_node."
                )
            ]
        )

    # 4. ARRAY / TWO POINTERS / SLIDING WINDOW
    elif "two pointer" in t_lower or "palindrome" in t_lower or "window" in t_lower or "sliding" in t_lower or "two sum" in t_lower:
        return VisualizationSpec(
            viz_type="array",
            title="Two Pointers: Inward Monotonic Scan",
            initial_state=[2, 7, 11, 15, 19, 23],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="inspect",
                    pointer="L=0 (val 2), R=5 (val 23)",
                    highlight_indices=[0, 5],
                    explanation="Target = 26. Compute sum: 2 + 23 = 25. Since 25 < 26, increment L."
                ),
                VisualizationStep(
                    step_number=2,
                    action="advance_pointer",
                    pointer="L=1 (val 7), R=5 (val 23)",
                    highlight_indices=[1, 5],
                    explanation="L moves to index 1 (val 7). Compute sum: 7 + 23 = 30. Since 30 > 26, decrement R."
                ),
                VisualizationStep(
                    step_number=3,
                    action="advance_pointer",
                    pointer="L=1 (val 7), R=4 (val 19)",
                    highlight_indices=[1, 4],
                    explanation="R moves to index 4 (val 19). Compute sum: 7 + 19 = 26! Target match found."
                )
            ]
        )

    # 5. SORTING
    elif "sort" in t_lower or "bubble" in t_lower or "merge" in t_lower or "quick" in t_lower:
        return VisualizationSpec(
            viz_type="sorting",
            title="Comparison-Based Sorting (Bubble / Step Swaps)",
            initial_state=[64, 34, 25, 12, 22, 11, 90],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="compare",
                    pointer="Compare arr[0] and arr[1]",
                    highlight_indices=[0, 1],
                    explanation="Compare 64 and 34. 64 > 34, so a swap is required."
                ),
                VisualizationStep(
                    step_number=2,
                    action="swap",
                    value={"from": 0, "to": 1},
                    pointer="Swap arr[0] <-> arr[1]",
                    highlight_indices=[0, 1],
                    explanation="Swap elements: array becomes [34, 64, 25, 12, 22, 11, 90]."
                ),
                VisualizationStep(
                    step_number=3,
                    action="compare",
                    pointer="Compare arr[1] and arr[2]",
                    highlight_indices=[1, 2],
                    explanation="Compare 64 and 25. 64 > 25, so swap again."
                ),
                VisualizationStep(
                    step_number=4,
                    action="swap",
                    value={"from": 1, "to": 2},
                    pointer="Swap arr[1] <-> arr[2]",
                    highlight_indices=[1, 2],
                    explanation="Swap elements: array becomes [34, 25, 64, 12, 22, 11, 90]."
                )
            ]
        )

    # 6. RECURSION / CALL STACK
    elif "recursion" in t_lower or "call stack" in t_lower or "factorial" in t_lower or "fibonacci" in t_lower:
        return VisualizationSpec(
            viz_type="recursion",
            title="Execution Call Stack (Frames Growth & Unwinding)",
            initial_state=[],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="call",
                    value="fact(3)",
                    pointer="SP -> Frame 1",
                    highlight_indices=[0],
                    explanation="fact(3) called: pushes frame onto execution stack. Needs 3 * fact(2)."
                ),
                VisualizationStep(
                    step_number=2,
                    action="call",
                    value="fact(2)",
                    pointer="SP -> Frame 2",
                    highlight_indices=[1],
                    explanation="fact(2) called: pushes frame. Needs 2 * fact(1)."
                ),
                VisualizationStep(
                    step_number=3,
                    action="call",
                    value="fact(1)",
                    pointer="SP -> Frame 3",
                    highlight_indices=[2],
                    explanation="fact(1) called: base case reached! Returns 1 immediately without further calls."
                ),
                VisualizationStep(
                    step_number=4,
                    action="return",
                    value="fact(1) returns 1 -> fact(2) returns 2*1=2 -> fact(3) returns 3*2=6",
                    pointer="SP unwinding",
                    highlight_indices=[0],
                    explanation="Frames unwind: fact(2) returns 2, fact(3) computes 3*2=6 and pops."
                )
            ]
        )

    # 7. TREES
    elif "tree" in t_lower or "bst" in t_lower or "binary tree" in t_lower:
        return VisualizationSpec(
            viz_type="tree",
            title="Binary Search Tree Traversal (In-Order: Left -> Root -> Right)",
            initial_state={
                "nodes": [
                    {"id": "A", "val": 8, "x": 50, "y": 20},
                    {"id": "B", "val": 3, "x": 25, "y": 50},
                    {"id": "C", "val": 10, "x": 75, "y": 50},
                    {"id": "D", "val": 1, "x": 12, "y": 80},
                    {"id": "E", "val": 6, "x": 38, "y": 80}
                ],
                "edges": [
                    {"from": "A", "to": "B"},
                    {"from": "A", "to": "C"},
                    {"from": "B", "to": "D"},
                    {"from": "B", "to": "E"}
                ]
            },
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="visit",
                    pointer="Visiting Node B (val 3)",
                    highlight_indices=[1],
                    explanation="Descend to left child: Node B (val 3). Traversal proceeds down to left leaf D."
                ),
                VisualizationStep(
                    step_number=2,
                    action="process",
                    pointer="Output Node D (val 1)",
                    highlight_indices=[3],
                    explanation="Leftmost leaf reached: process Node D (val 1). Output = [1]."
                ),
                VisualizationStep(
                    step_number=3,
                    action="process",
                    pointer="Backtrack & Output Node B (val 3)",
                    highlight_indices=[1],
                    explanation="Backtrack to parent B: process Node B (val 3). Output = [1, 3]."
                ),
                VisualizationStep(
                    step_number=4,
                    action="visit",
                    pointer="Visit right child Node E (val 6)",
                    highlight_indices=[4],
                    explanation="Descend to right child Node E: process Node E (val 6). Output = [1, 3, 6]."
                )
            ]
        )

    # 7B. ALIEN DICTIONARY / TOPOLOGICAL SORT (DAG)
    elif "alien" in t_lower or "topological" in t_lower or "kahn" in t_lower or "dag" in t_lower:
        return VisualizationSpec(
            viz_type="alien_dictionary",
            title="Alien Dictionary — Topological Sort (Kahn's Algorithm)",
            initial_state={
                "nodes": ["w", "e", "r", "t", "f"],
                "edges": [["w", "e"], ["e", "r"], ["r", "t"], ["t", "f"]],
                "in_degrees": {"w": 0, "e": 1, "r": 1, "t": 1, "f": 1},
                "order": []
            },
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="build_dag",
                    pointer="In-Degrees: w:0, e:1, r:1, t:1, f:1",
                    highlight_indices=[0],
                    explanation="Compare adjacent words to extract character order rules: 'w' -> 'e' -> 'r' -> 't' -> 'f'. Compute in-degrees: only 'w' has in-degree 0."
                ),
                VisualizationStep(
                    step_number=2,
                    action="process_node",
                    value="w",
                    pointer="Queue: [e] | Resolved Order: ['w']",
                    highlight_indices=[0, 1],
                    explanation="Enqueue 'w' (in-degree 0). Remove 'w': decrement neighbor 'e' in-degree to 0. Enqueue 'e'. Append 'w' to order."
                ),
                VisualizationStep(
                    step_number=3,
                    action="process_node",
                    value="e",
                    pointer="Queue: [r] | Resolved Order: ['w', 'e']",
                    highlight_indices=[1, 2],
                    explanation="Process 'e'. Decrement neighbor 'r' in-degree to 0. Enqueue 'r'. Append 'e' to order."
                ),
                VisualizationStep(
                    step_number=4,
                    action="process_node",
                    value="r",
                    pointer="Queue: [t] | Resolved Order: ['w', 'e', 'r']",
                    highlight_indices=[2, 3],
                    explanation="Process 'r'. Decrement neighbor 't' in-degree to 0. Enqueue 't'. Append 'r' to order."
                ),
                VisualizationStep(
                    step_number=5,
                    action="process_node",
                    value="t -> f",
                    pointer="Queue: [] | Final Alien Order: 'wertf'",
                    highlight_indices=[3, 4],
                    explanation="Process 't' then 'f'. All 5 unique characters processed with 0 remaining in-degrees. Valid Alien alphabet order: 'wertf'!"
                )
            ]
        )

    # 8. GRAPHS
    elif "graph" in t_lower or "bfs" in t_lower or "dfs" in t_lower:
        return VisualizationSpec(
            viz_type="graph",
            title="Breadth-First Search (BFS) Wavefront Traversal",
            initial_state={
                "nodes": [
                    {"id": 0, "label": "Start(0)", "x": 20, "y": 50},
                    {"id": 1, "label": "Node(1)", "x": 50, "y": 20},
                    {"id": 2, "label": "Node(2)", "x": 50, "y": 80},
                    {"id": 3, "label": "Target(3)", "x": 80, "y": 50}
                ],
                "edges": [
                    {"from": 0, "to": 1},
                    {"from": 0, "to": 2},
                    {"from": 1, "to": 3},
                    {"from": 2, "to": 3}
                ]
            },
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="visit",
                    pointer="Enqueue 0 | Visited: {0}",
                    highlight_indices=[0],
                    explanation="Enqueue start node 0. Mark 0 as visited at distance 0."
                ),
                VisualizationStep(
                    step_number=2,
                    action="expand",
                    pointer="Dequeue 0 -> Enqueue 1, 2 | Visited: {0, 1, 2}",
                    highlight_indices=[1, 2],
                    explanation="Explore neighbors of 0: nodes 1 and 2 are added to the BFS queue at distance 1."
                ),
                VisualizationStep(
                    step_number=3,
                    action="target_found",
                    pointer="Dequeue 1 -> Discover Target(3) | Dist=2",
                    highlight_indices=[3],
                    explanation="Dequeue node 1, discover neighbor 3 (Target). Shortest path is 0 -> 1 -> 3 (dist 2)!"
                )
            ]
        )

    # 9. POINTERS / MEMORY
    elif "pointer" in t_lower or "address" in t_lower or "memory" in t_lower or "reference" in t_lower:
        return VisualizationSpec(
            viz_type="pointers",
            title="Memory Addresses & Pointer Dereferencing (*ptr)",
            initial_state=[
                {"var": "x", "addr": "0x7ffd01", "val": 42, "type": "int"},
                {"var": "ptr", "addr": "0x7ffd08", "val": "0x7ffd01", "type": "int*"}
            ],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="inspect",
                    pointer="ptr holds 0x7ffd01",
                    highlight_indices=[1],
                    explanation="Variable 'ptr' is stored at address 0x7ffd08. Its value is the memory address of 'x' (0x7ffd01)."
                ),
                VisualizationStep(
                    step_number=2,
                    action="dereference",
                    pointer="*ptr dereferences to x",
                    highlight_indices=[0, 1],
                    explanation="Dereference '*ptr': follows pointer address to memory location 0x7ffd01, reading value 42."
                ),
                VisualizationStep(
                    step_number=3,
                    action="mutate",
                    value="*ptr = 100",
                    pointer="x becomes 100",
                    highlight_indices=[0],
                    explanation="Assign '*ptr = 100': directly mutates the memory cell of 'x'. 'x' is now 100."
                )
            ]
        )

    # 10. SEARCHING (BINARY SEARCH)
    elif "search" in t_lower or "binary search" in t_lower:
        return VisualizationSpec(
            viz_type="searching",
            title="Binary Search (Interval Halving)",
            initial_state=[3, 8, 14, 21, 27, 33, 49, 58, 67, 82],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="inspect",
                    pointer="low=0, mid=4 (val 27), high=9",
                    highlight_indices=[0, 4, 9],
                    explanation="Search for target 58. Inspect middle index 4 (val 27). 27 < 58: eliminate left half."
                ),
                VisualizationStep(
                    step_number=2,
                    action="eliminate",
                    pointer="low=5, mid=7 (val 58), high=9",
                    highlight_indices=[5, 7, 9],
                    explanation="Search region is now [5..9]. Inspect new mid index 7 (val 58). 58 == 58! Match found."
                ),
                VisualizationStep(
                    step_number=3,
                    action="match",
                    pointer="Match found at index 7",
                    highlight_indices=[7],
                    explanation="Target 58 located at index 7 in O(log N) comparisons."
                )
            ]
        )

    # Hash Table / Hash Map — only when explicitly requested
    if t_lower in ("hash table", "hash map", "hashmap", "hash", "hash set", "hashing"):
        return VisualizationSpec(
            viz_type="array",
            title="Hash Map Bucket Lookup",
            initial_state=["[0] Empty", "[1] ('target', 42)", "[2] Empty", "[3] ('key', 99)"],
            steps=[
                VisualizationStep(
                    step_number=1,
                    action="hash",
                    pointer="hash('target') % 4 = 1",
                    highlight_indices=[1],
                    explanation="Hash function maps key 'target' to bucket index 1 in O(1) time."
                ),
                VisualizationStep(
                    step_number=2,
                    action="lookup",
                    pointer="Read value 42",
                    highlight_indices=[1],
                    explanation="Direct index probe into bucket 1 retrieves value 42 without any sequential search."
                )
            ]
        )

    # No visualization available for unrecognized topics — return None gracefully
    return None

