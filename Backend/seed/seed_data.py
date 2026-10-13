"""
Seed dataset containing original problem definitions to verify the CodeMind Phase 1 architecture.
All statements are original or attribution-annotated sample problems.
"""

from typing import List, Dict, Any

SEED_PROBLEMS: List[Dict[str, Any]] = [
    {
        "id": "two-sum-target",
        "title": "Two Sum Target",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/two-sum-target",
        "external_id": "CM-001",
        "problem_type": "Interview",
        "difficulty": "Easy",
        "rating": None,
        "domains": ["Arrays", "Hash Map"],
        "tags": ["array", "hash-table", "two-pointers"],
        "concepts": ["Hash Table Lookup", "Index Mapping", "Time-Space Tradeoff"],
        "prerequisites": ["Basic Array Iteration", "Dictionaries/Hash Maps"],
        "description": "Given an integer array `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.\n\nYou may assume that each input has exactly one solution, and you may not use the same element twice. You can return the answer in any order.",
        "input_format": "The first line contains an array of integers `nums`. The second line contains an integer `target`.",
        "output_format": "Return a list of two integer indices `[index1, index2]`.",
        "examples": [
            {
                "input": "nums = [2, 7, 11, 15], target = 9",
                "output": "[0, 1]",
                "explanation": "Because nums[0] + nums[1] == 2 + 7 == 9, we return [0, 1]."
            },
            {
                "input": "nums = [3, 2, 4], target = 6",
                "output": "[1, 2]",
                "explanation": "nums[1] + nums[2] == 2 + 4 == 6, so return [1, 2]."
            }
        ],
        "constraints": [
            "2 <= nums.length <= 10^4",
            "-10^9 <= nums[i] <= 10^9",
            "-10^9 <= target <= 10^9",
            "Exactly one valid answer exists."
        ],
        "starter_code": {
            "python": "def two_sum(nums: list[int], target: int) -> list[int]:\n    # Write your solution here\n    pass\n",
            "cpp": "#include <vector>\nusing namespace std;\n\nclass Solution {\npublic:\n    vector<int> twoSum(vector<int>& nums, int target) {\n        // Write your solution here\n    }\n};"
        },
        "supported_languages": ["python", "cpp", "java", "javascript"]
    },
    {
        "id": "valid-palindrome-phrase",
        "title": "Valid Palindrome Phrase",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/valid-palindrome-phrase",
        "external_id": "CM-002",
        "problem_type": "Interview",
        "difficulty": "Easy",
        "rating": None,
        "domains": ["Strings", "Two Pointers"],
        "tags": ["string", "two-pointers"],
        "concepts": ["Two Pointers", "String Sanitization"],
        "prerequisites": ["ASCII / Character manipulation", "While loops"],
        "description": "A phrase is a palindrome if, after converting all uppercase letters into lowercase letters and removing all non-alphanumeric characters, it reads the same forward and backward.\n\nGiven a string `s`, return `True` if it is a palindrome, or `False` otherwise.",
        "input_format": "A single string `s` containing ASCII characters.",
        "output_format": "Boolean `True` or `False`.",
        "examples": [
            {
                "input": "s = \"A man, a plan, a canal: Panama\"",
                "output": "True",
                "explanation": "\"amanaplanacanalpanama\" is a palindrome."
            },
            {
                "input": "s = \"race a car\"",
                "output": "False",
                "explanation": "\"raceacar\" is not a palindrome."
            }
        ],
        "constraints": [
            "1 <= s.length <= 2 * 10^5",
            "s consists only of printable ASCII characters."
        ],
        "starter_code": {
            "python": "def is_palindrome(s: str) -> bool:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "javascript"]
    },
    {
        "id": "reverse-singly-linked-list",
        "title": "Reverse Singly Linked List",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/reverse-singly-linked-list",
        "external_id": "CM-003",
        "problem_type": "Data Structures",
        "difficulty": "Easy",
        "rating": None,
        "domains": ["Linked Lists"],
        "tags": ["linked-list", "pointers", "iteration"],
        "concepts": ["Pointer Manipulation", "Iterative In-place Reversal"],
        "prerequisites": ["Node References", "Pointers"],
        "description": "Given the head of a singly linked list, reverse the list, and return the reversed list's new head.",
        "input_format": "The head node of a linked list.",
        "output_format": "The head node of the reversed linked list.",
        "examples": [
            {
                "input": "head = [1, 2, 3, 4, 5]",
                "output": "[5, 4, 3, 2, 1]",
                "explanation": "Pointers are inverted so node 5 points to 4, etc."
            }
        ],
        "constraints": [
            "The number of nodes in the list is in the range [0, 5000].",
            "-5000 <= Node.val <= 5000"
        ],
        "starter_code": {
            "python": "class ListNode:\n    def __init__(self, val=0, next=None):\n        self.val = val\n        self.next = next\n\ndef reverse_list(head: ListNode) -> ListNode:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "balanced-brackets-checker",
        "title": "Balanced Brackets Checker",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/balanced-brackets-checker",
        "external_id": "CM-004",
        "problem_type": "Data Structures",
        "difficulty": "Easy",
        "rating": None,
        "domains": ["Stack", "Strings"],
        "tags": ["stack", "parsing", "parentheses"],
        "concepts": ["LIFO Stack Order", "Matching Delimiters"],
        "prerequisites": ["Stack ADT", "Dictionary mapping"],
        "description": "Given a string `s` containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid.\n\nAn input string is valid if open brackets are closed by the same type of brackets in the correct order.",
        "input_format": "A string `s` of bracket characters.",
        "output_format": "Boolean `True` or `False`.",
        "examples": [
            {
                "input": "s = \"()[]{}\"",
                "output": "True",
                "explanation": "Every opening bracket is properly closed."
            },
            {
                "input": "s = \"(]\"",
                "output": "False",
                "explanation": "Opening round bracket is improperly closed with a square bracket."
            }
        ],
        "constraints": [
            "1 <= s.length <= 10^4",
            "s consists of parentheses only '()[]{}'."
        ],
        "starter_code": {
            "python": "def is_valid_brackets(s: str) -> bool:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java", "javascript"]
    },
    {
        "id": "circular-queue-buffer",
        "title": "Design Circular Buffer",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/circular-queue-buffer",
        "external_id": "CM-005",
        "problem_type": "Implementation",
        "difficulty": "Medium",
        "rating": None,
        "domains": ["Queue", "Arrays", "Object-Oriented Programming"],
        "tags": ["queue", "circular-buffer", "design"],
        "concepts": ["Modulo Arithmetic for Ring Buffers", "Fixed-size Data Structures"],
        "prerequisites": ["Array indexing", "Modulo operations"],
        "description": "Design your implementation of the circular queue (ring buffer). A circular queue is a linear data structure in which the operations are performed based on FIFO principle and the last position is connected back to the first position to make a circle.",
        "input_format": "Method invocations on MyCircularQueue(k).",
        "output_format": "Return values for enQueue, deQueue, Front, Rear, isEmpty, isFull.",
        "examples": [
            {
                "input": "MyCircularQueue(3); enQueue(1); enQueue(2); enQueue(3); enQueue(4); Rear(); isFull(); deQueue(); enQueue(4); Rear()",
                "output": "[true, true, true, false, 3, true, true, true, 4]",
                "explanation": "Buffer stores up to 3 elements. 4th enQueue fails because queue is full."
            }
        ],
        "constraints": [
            "1 <= k <= 1000",
            "0 <= value <= 1000",
            "At most 3000 calls will be made."
        ],
        "starter_code": {
            "python": "class MyCircularQueue:\n    def __init__(self, k: int):\n        pass\n\n    def enQueue(self, value: int) -> bool:\n        pass\n\n    def deQueue(self) -> bool:\n        pass\n\n    def Front(self) -> int:\n        pass\n\n    def Rear(self) -> int:\n        pass\n\n    def isEmpty(self) -> bool:\n        pass\n\n    def isFull(self) -> bool:\n        pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "k-frequent-elements",
        "title": "Top K Frequent Elements",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/k-frequent-elements",
        "external_id": "CM-006",
        "problem_type": "Algorithms",
        "difficulty": "Medium",
        "rating": None,
        "domains": ["Hash Map", "Heap / Priority Queue", "Sorting"],
        "tags": ["heap", "frequency-count", "bucket-sort"],
        "concepts": ["Min-Heap of Size K", "Bucket Sort", "Frequency Map"],
        "prerequisites": ["Priority Queues", "Hash Tables"],
        "description": "Given an integer array `nums` and an integer `k`, return the `k` most frequent elements. You may return the answer in any order.",
        "input_format": "An array of integers `nums` and an integer `k`.",
        "output_format": "An array of `k` integers.",
        "examples": [
            {
                "input": "nums = [1,1,1,2,2,3], k = 2",
                "output": "[1, 2]",
                "explanation": "1 occurs 3 times, 2 occurs 2 times. The top 2 elements are [1, 2]."
            }
        ],
        "constraints": [
            "1 <= nums.length <= 10^5",
            "-10^4 <= nums[i] <= 10^4",
            "k is in the range [1, the number of unique elements in the array]."
        ],
        "starter_code": {
            "python": "def top_k_frequent(nums: list[int], k: int) -> list[int]:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "maximum-subarray-sum",
        "title": "Maximum Subarray Sum",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/maximum-subarray-sum",
        "external_id": "CM-007",
        "problem_type": "Algorithms",
        "difficulty": "Medium",
        "rating": None,
        "domains": ["Arrays", "Dynamic Programming", "Prefix Sum"],
        "tags": ["kadane", "dynamic-programming", "divide-and-conquer"],
        "concepts": ["Kadane's Algorithm", "Local vs Global Optimum"],
        "prerequisites": ["Arrays", "Greedy / DP transitions"],
        "description": "Given an integer array `nums`, find the subarray with the largest sum, and return its sum.",
        "input_format": "An array of integers `nums`.",
        "output_format": "An integer representing the maximum subarray sum.",
        "examples": [
            {
                "input": "nums = [-2, 1, -3, 4, -1, 2, 1, -5, 4]",
                "output": "6",
                "explanation": "The subarray [4, -1, 2, 1] has the largest sum 6."
            }
        ],
        "constraints": [
            "1 <= nums.length <= 10^5",
            "-10^4 <= nums[i] <= 10^4"
        ],
        "starter_code": {
            "python": "def max_sub_array(nums: list[int]) -> int:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "climbing-staircase-ways",
        "title": "Climbing Staircase Distinct Ways",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/climbing-staircase-ways",
        "external_id": "CM-008",
        "problem_type": "Algorithms",
        "difficulty": "Easy",
        "rating": None,
        "domains": ["Dynamic Programming", "Recursion"],
        "tags": ["dp", "fibonacci", "memoization"],
        "concepts": ["1D Dynamic Programming", "Recurrence Relations"],
        "prerequisites": ["Basic Recursion"],
        "description": "You are climbing a staircase. It takes `n` steps to reach the top. Each time you can either climb 1 or 2 steps. In how many distinct ways can you climb to the top?",
        "input_format": "A single integer `n`.",
        "output_format": "An integer denoting the number of distinct ways.",
        "examples": [
            {
                "input": "n = 3",
                "output": "3",
                "explanation": "Ways: (1+1+1), (1+2), (2+1)."
            }
        ],
        "constraints": [
            "1 <= n <= 45"
        ],
        "starter_code": {
            "python": "def climb_stairs(n: int) -> int:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java", "javascript"]
    },
    {
        "id": "binary-tree-inorder-traversal",
        "title": "Binary Tree Inorder Traversal",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/binary-tree-inorder-traversal",
        "external_id": "CM-009",
        "problem_type": "Data Structures",
        "difficulty": "Easy",
        "rating": None,
        "domains": ["Trees", "Binary Trees", "DFS"],
        "tags": ["tree", "dfs", "recursion"],
        "concepts": ["Depth First Search", "Inorder Property (Left-Root-Right)"],
        "prerequisites": ["Binary Tree representation"],
        "description": "Given the root of a binary tree, return the inorder traversal of its nodes' values.",
        "input_format": "The root node of a binary tree.",
        "output_format": "A list of node values in inorder sequence.",
        "examples": [
            {
                "input": "root = [1, null, 2, 3]",
                "output": "[1, 3, 2]",
                "explanation": "Node 1 is root, node 2 is right child with left child 3."
            }
        ],
        "constraints": [
            "The number of nodes in the tree is in the range [0, 100].",
            "-100 <= Node.val <= 100"
        ],
        "starter_code": {
            "python": "class TreeNode:\n    def __init__(self, val=0, left=None, right=None):\n        self.val = val\n        self.left = left\n        self.right = right\n\ndef inorder_traversal(root: TreeNode) -> list[int]:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "validate-binary-search-tree",
        "title": "Validate Binary Search Tree",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/validate-binary-search-tree",
        "external_id": "CM-010",
        "problem_type": "Data Structures",
        "difficulty": "Medium",
        "rating": None,
        "domains": ["Binary Search Trees", "Trees", "DFS"],
        "tags": ["bst", "recursion", "tree-validation"],
        "concepts": ["BST Invariant", "Subtree Range Validation"],
        "prerequisites": ["Binary Search Tree Properties"],
        "description": "Given the root of a binary tree, determine if it is a valid binary search tree (BST).\n\nA valid BST is defined as follows:\n- The left subtree of a node contains only nodes with keys strictly less than the node's key.\n- The right subtree of a node contains only nodes with keys strictly greater than the node's key.\n- Both the left and right subtrees must also be binary search trees.",
        "input_format": "Root node of a binary tree.",
        "output_format": "Boolean `True` or `False`.",
        "examples": [
            {
                "input": "root = [2, 1, 3]",
                "output": "True",
                "explanation": "Left child 1 < 2 < Right child 3."
            },
            {
                "input": "root = [5, 1, 4, null, null, 3, 6]",
                "output": "False",
                "explanation": "The root value is 5, but its right child value is 4."
            }
        ],
        "constraints": [
            "The number of nodes in the tree is in the range [1, 10^4].",
            "-2^31 <= Node.val <= 2^31 - 1"
        ],
        "starter_code": {
            "python": "class TreeNode:\n    def __init__(self, val=0, left=None, right=None):\n        self.val = val\n        self.left = left\n        self.right = right\n\ndef is_valid_bst(root: TreeNode) -> bool:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "clone-undirected-graph",
        "title": "Clone Undirected Graph",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/clone-undirected-graph",
        "external_id": "CM-011",
        "problem_type": "Algorithms",
        "difficulty": "Medium",
        "rating": None,
        "domains": ["Graphs", "BFS", "DFS", "Hash Map"],
        "tags": ["graph", "bfs", "dfs", "hash-map"],
        "concepts": ["Deep Copying Graphs", "Visited Tracking via Hash Map"],
        "prerequisites": ["Graph Representation", "Recursion / Queue for BFS"],
        "description": "Given a reference of a node in a connected undirected graph, return a deep copy (clone) of the graph.\n\nEach node in the graph contains a value `val` (int) and a list `neighbors` (List[Node]).",
        "input_format": "Reference node of a connected undirected graph.",
        "output_format": "Reference node of the cloned graph.",
        "examples": [
            {
                "input": "adjList = [[2,4],[1,3],[2,4],[1,3]]",
                "output": "[[2,4],[1,3],[2,4],[1,3]]",
                "explanation": "A complete duplicate of 4 connected nodes with same structure but distinct memory addresses."
            }
        ],
        "constraints": [
            "The number of nodes in the graph is in the range [0, 100].",
            "1 <= Node.val <= 100",
            "Node.val is unique for each node."
        ],
        "starter_code": {
            "python": "class Node:\n    def __init__(self, val = 0, neighbors = None):\n        self.val = val\n        self.neighbors = neighbors if neighbors is not None else []\n\ndef clone_graph(node: 'Node') -> 'Node':\n    # Write your solution here\n    pass\n",
            "c": "/**\n * Definition for a Node.\n * struct Node {\n *     int val;\n *     int numNeighbors;\n *     struct Node** neighbors;\n * };\n */\n#include <stdio.h>\n#include <stdlib.h>\n\nstruct Node {\n    int val;\n    int numNeighbors;\n    struct Node** neighbors;\n};\n\nstruct Node* cloneGraph(struct Node* node) {\n    // Write your solution here\n    return NULL;\n}\n"
        },
        "supported_languages": ["python", "c", "cpp", "java"]
    },
    {
        "id": "number-of-islands-grid",
        "title": "Number of Islands in Grid",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/number-of-islands-grid",
        "external_id": "CM-012",
        "problem_type": "Algorithms",
        "difficulty": "Medium",
        "rating": None,
        "domains": ["Graphs", "BFS", "DFS", "Arrays"],
        "tags": ["grid", "bfs", "dfs", "connected-components"],
        "concepts": ["Flood Fill", "2D Grid Traversal", "Connected Components"],
        "prerequisites": ["2D Matrix indexing", "Queue or Recursion"],
        "description": "Given an `m x n` 2D binary grid `grid` which represents a map of `'1'`s (land) and `'0'`s (water), return the number of islands.\n\nAn island is surrounded by water and is formed by connecting adjacent lands horizontally or vertically. You may assume all four edges of the grid are all surrounded by water.",
        "input_format": "A 2D list of characters `grid`.",
        "output_format": "An integer count of islands.",
        "examples": [
            {
                "input": "grid = [[\"1\",\"1\",\"0\",\"0\",\"0\"],[\"1\",\"1\",\"0\",\"0\",\"0\"],[\"0\",\"0\",\"1\",\"0\",\"0\"],[\"0\",\"0\",\"0\",\"1\",\"1\"]]",
                "output": "3",
                "explanation": "There are three distinct connected components of 1s."
            }
        ],
        "constraints": [
            "m == grid.length",
            "n == grid[i].length",
            "1 <= m, n <= 300",
            "grid[i][j] is '0' or '1'."
        ],
        "starter_code": {
            "python": "def num_islands(grid: list[list[str]]) -> int:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "longest-substring-distinct-k",
        "title": "Longest Substring with At Most K Distinct Characters",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/longest-substring-distinct-k",
        "external_id": "CM-013",
        "problem_type": "Interview",
        "difficulty": "Hard",
        "rating": None,
        "domains": ["Strings", "Sliding Window", "Hash Map"],
        "tags": ["sliding-window", "strings", "hash-map"],
        "concepts": ["Dynamic Window Sizing", "Frequency Map in Sliding Window"],
        "prerequisites": ["Sliding Window Technique", "Hash Map"],
        "description": "Given a string `s` and an integer `k`, return the length of the longest substring of `s` that contains at most `k` distinct characters.",
        "input_format": "A string `s` and an integer `k`.",
        "output_format": "An integer representing the maximum substring length.",
        "examples": [
            {
                "input": "s = \"eceba\", k = 2",
                "output": "3",
                "explanation": "The substring is \"ece\" with length 3 containing 'e' and 'c'."
            },
            {
                "input": "s = \"aa\", k = 1",
                "output": "2",
                "explanation": "\"aa\" has 1 distinct character and length 2."
            }
        ],
        "constraints": [
            "1 <= s.length <= 5 * 10^4",
            "0 <= k <= 50"
        ],
        "starter_code": {
            "python": "def length_of_longest_substring_k_distinct(s: str, k: int) -> int:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "coin-change-minimum",
        "title": "Fewest Coins for Change",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/coin-change-minimum",
        "external_id": "CM-014",
        "problem_type": "Algorithms",
        "difficulty": "Medium",
        "rating": None,
        "domains": ["Dynamic Programming", "BFS"],
        "tags": ["knapsack", "dp", "bfs", "unbounded-knapsack"],
        "concepts": ["Unbounded Knapsack", "Bottom-up DP Array"],
        "prerequisites": ["Dynamic Programming fundamentals"],
        "description": "You are given an integer array `coins` representing coins of different denominations and an integer `amount` representing a total amount of money.\n\nReturn the fewest number of coins that you need to make up that amount. If that amount of money cannot be made up by any combination of the coins, return -1.\n\nYou may assume that you have an infinite number of each kind of coin.",
        "input_format": "An array of positive integers `coins` and an integer `amount`.",
        "output_format": "An integer representing minimum coins needed, or -1.",
        "examples": [
            {
                "input": "coins = [1, 2, 5], amount = 11",
                "output": "3",
                "explanation": "11 = 5 + 5 + 1 (3 coins)."
            },
            {
                "input": "coins = [2], amount = 3",
                "output": "-1",
                "explanation": "Cannot make amount 3 using only 2."
            },
            {
                "input": "coins = [1, 3, 4], amount = 6",
                "output": "2",
                "explanation": "Optimal is 3 + 3 = 6 (2 coins), while greedy picks 4 + 1 + 1 (3 coins)."
            }
        ],
        "constraints": [
            "1 <= coins.length <= 12",
            "1 <= coins[i] <= 2^31 - 1",
            "0 <= amount <= 10^4"
        ],
        "starter_code": {
            "python": "def coin_change(coins: list[int], amount: int) -> int:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "alien-dictionary-order",
        "title": "Alien Dictionary Ordering",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/alien-dictionary-order",
        "external_id": "CM-015",
        "problem_type": "Interview",
        "difficulty": "Hard",
        "rating": None,
        "domains": ["Graphs", "Topological Sort", "Strings"],
        "tags": ["topological-sort", "dag", "graph", "kahn-algorithm"],
        "concepts": ["Directed Acyclic Graph (DAG)", "Kahn's Algorithm / In-degree"],
        "prerequisites": ["Topological Sort", "Graph Adjacency List"],
        "description": "There is a new alien language that uses the English alphabet. However, the order of the letters is unknown to you.\n\nYou are given a list of strings `words` from the alien language's dictionary, where the strings are claimed to be sorted lexicographically by the rules of this new language.\n\nReturn a string of the unique letters in the new alien language sorted in lexicographically increasing order by the new language's rules. If there is no solution, return \"\".",
        "input_format": "A list of strings `words`.",
        "output_format": "A string of alphabet characters in alien order.",
        "examples": [
            {
                "input": "words = [\"wrt\",\"wrf\",\"er\",\"ett\",\"rftt\"]",
                "output": "\"wertf\"",
                "explanation": "Comparing pairs gives w -> e -> r -> t -> f."
            }
        ],
        "constraints": [
            "1 <= words.length <= 100",
            "1 <= words[i].length <= 100",
            "words[i] consists of only lowercase English letters."
        ],
        "starter_code": {
            "python": "def alien_order(words: list[str]) -> str:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "fast-modular-exponentiation",
        "title": "Fast Modular Exponentiation",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/fast-modular-exponentiation",
        "external_id": "CM-016",
        "problem_type": "Mathematics",
        "difficulty": "Medium",
        "rating": None,
        "domains": ["Mathematics", "Number Theory", "Modular Arithmetic"],
        "tags": ["binary-exponentiation", "math", "modulo"],
        "concepts": ["Binary Exponentiation", "O(log n) Power Computation"],
        "prerequisites": ["Modular Arithmetic Rules"],
        "description": "Compute `(base^exponent) % mod` efficiently in `O(log exponent)` time without causing integer overflow.\n\nGiven integers `base`, `exponent`, and `mod`, return the remainder of `base` raised to `exponent` divided by `mod`.",
        "input_format": "Three integers: `base`, `exponent`, and `mod`.",
        "output_format": "An integer remainder.",
        "examples": [
            {
                "input": "base = 2, exponent = 10, mod = 1000",
                "output": "24",
                "explanation": "2^10 = 1024, 1024 % 1000 = 24."
            },
            {
                "input": "base = 3, exponent = 13, mod = 1000000007",
                "output": "1594323",
                "explanation": "3^13 % 10^9+7 = 1594323."
            }
        ],
        "constraints": [
            "1 <= base <= 10^9",
            "0 <= exponent <= 10^18",
            "1 <= mod <= 10^9"
        ],
        "starter_code": {
            "python": "def power_mod(base: int, exponent: int, mod: int) -> int:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "bitwise-single-number",
        "title": "Find the Single Unique Element",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/bitwise-single-number",
        "external_id": "CM-017",
        "problem_type": "Algorithms",
        "difficulty": "Easy",
        "rating": None,
        "domains": ["Bit Manipulation"],
        "tags": ["bitwise-xor", "bit-manipulation"],
        "concepts": ["XOR Self-Inverse Property (a ^ a = 0)"],
        "prerequisites": ["Bitwise Operators"],
        "description": "Given a non-empty array of integers `nums`, every element appears twice except for one. Find that single one.\n\nYou must implement a solution with a linear runtime complexity and use only constant extra space.",
        "input_format": "An array of integers `nums`.",
        "output_format": "An integer representing the unique element.",
        "examples": [
            {
                "input": "nums = [4, 1, 2, 1, 2]",
                "output": "4",
                "explanation": "1 and 2 appear twice, 4 appears once."
            }
        ],
        "constraints": [
            "1 <= nums.length <= 3 * 10^4",
            "-3 * 10^4 <= nums[i] <= 3 * 10^4",
            "Each element in the array appears twice except for one element which appears only once."
        ],
        "starter_code": {
            "python": "def single_number(nums: list[int]) -> int:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java", "javascript"]
    },
    {
        "id": "codeforces-watermelon-split",
        "title": "Watermelon Parity Split",
        "source": "Codeforces",
        "source_url": "https://codeforces.com/problemset/problem/4/A",
        "external_id": "CF-4A",
        "problem_type": "Competitive Programming",
        "difficulty": "Beginner",
        "rating": 800,
        "domains": ["Mathematics", "Competitive Programming", "Programming Fundamentals"],
        "tags": ["math", "parity", "brute-force"],
        "concepts": ["Even Parity", "Boundary Condition Check"],
        "prerequisites": ["Conditional Statements"],
        "description": "One hot summer day Pete and his friend Billy decided to buy a watermelon. They chose the biggest and the ripest one, in their opinion. After that the watermelon was weighed, and the scales showed `w` kilos.\n\nThey rushed home, dying of thirst, and decided to divide the berry, however they faced a hard problem. Pete and Billy are great fans of even numbers, that's why they want to divide the watermelon into two parts, each of them weighing even number of kilos; and it is not obligatory that the parts are equal.\n\nHelp Pete and Billy: print YES, if they can divide the watermelon into two parts each of which has even weight; and NO in the opposite case.",
        "input_format": "The first (and the only) input line contains integer number `w` (1 <= w <= 100) — the weight of the watermelon bought by the boys.",
        "output_format": "Print YES, if the boys can divide the watermelon into two parts, each of them weighing an even number of kilos; and NO in the opposite case.",
        "examples": [
            {
                "input": "w = 8",
                "output": "\"YES\"",
                "explanation": "The boys can divide the watermelon into two parts of 2 and 6 kilos respectively (or 4 and 4 kilos)."
            },
            {
                "input": "w = 2",
                "output": "\"NO\"",
                "explanation": "2 can only be split into 1 and 1, which are odd numbers."
            }
        ],
        "constraints": [
            "1 <= w <= 100"
        ],
        "starter_code": {
            "python": "def can_split_watermelon(w: int) -> str:\n    # Return 'YES' or 'NO'\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    },
    {
        "id": "codeforces-cheap-travel-metro",
        "title": "Cheap Travel Subway Fare",
        "source": "Codeforces",
        "source_url": "https://codeforces.com/problemset/problem/466/A",
        "external_id": "CF-466A",
        "problem_type": "Competitive Programming",
        "difficulty": "Easy",
        "rating": 1200,
        "domains": ["Greedy", "Mathematics", "Competitive Programming"],
        "tags": ["greedy", "math", "implementation"],
        "concepts": ["Cost Optimization", "Greedy Choice Property"],
        "prerequisites": ["Basic arithmetic & conditionals"],
        "description": "Ann has planned to take `n` subway rides. A single ticket costs `a` rubles, while a special ticket valid for `m` rides costs `b` rubles. Ann wants to spend the minimum possible amount of money.\n\nHelp Ann calculate the minimum sum in rubles she needs to spend to make at least `n` rides.",
        "input_format": "Four integers: `n` (number of rides), `m` (rides per multi-ride ticket), `a` (single ticket cost), `b` (multi-ticket cost).",
        "output_format": "An integer representing the minimum total cost.",
        "examples": [
            {
                "input": "n = 6, m = 2, a = 1, b = 4",
                "output": "6",
                "explanation": "Single tickets are 1 ruble, 6 rides cost 6 * 1 = 6 rubles, which is cheaper than three 2-ride tickets for 12."
            },
            {
                "input": "n = 5, m = 2, a = 2, b = 3",
                "output": "8",
                "explanation": "Two 2-ride tickets cost 6 for 4 rides, plus one single ticket costs 2, total 8."
            }
        ],
        "constraints": [
            "1 <= n, m, a, b <= 1000"
        ],
        "starter_code": {
            "python": "def min_travel_cost(n: int, m: int, a: int, b: int) -> int:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp"]
    },
    {
        "id": "codeforces-longest-regular-bracket",
        "title": "Longest Regular Bracket Substring",
        "source": "Codeforces",
        "source_url": "https://codeforces.com/problemset/problem/5/C",
        "external_id": "CF-5C",
        "problem_type": "Competitive Programming",
        "difficulty": "Hard",
        "rating": 1900,
        "domains": ["Stack", "Dynamic Programming", "Competitive Programming"],
        "tags": ["dp", "stack", "strings"],
        "concepts": ["Stack Matching", "DP Prefix Expansion"],
        "prerequisites": ["Stack operations", "Dynamic Programming"],
        "description": "Given a bracket sequence consisting of '(' and ')', find the length of the longest regular bracket subsegment and the number of such subsegments of maximum length.",
        "input_format": "A single string consisting of parentheses characters.",
        "output_format": "Two integers separated by space: maximum length and frequency of occurrence.",
        "examples": [
            {
                "input": "s = \"(())\"",
                "output": "4 1",
                "explanation": "Entire string of length 4 is regular, appearing once."
            },
            {
                "input": "s = \")(\"",
                "output": "0 1",
                "explanation": "No regular substring of length > 0 exists; maximum length is 0, count is 1."
            }
        ],
        "constraints": [
            "1 <= s.length <= 10^6"
        ],
        "starter_code": {
            "python": "def longest_regular_bracket(s: str) -> tuple[int, int]:\n    # Return (max_length, count)\n    pass\n"
        },
        "supported_languages": ["python", "cpp"]
    },
    {
        "id": "simple-counter-oop",
        "title": "Bounded Step Counter Class",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/simple-counter-oop",
        "external_id": "CM-018",
        "problem_type": "Programming Fundamentals",
        "difficulty": "Beginner",
        "rating": None,
        "domains": ["Object-Oriented Programming", "Programming Fundamentals"],
        "tags": ["classes", "encapsulation", "oop"],
        "concepts": ["Encapsulation", "State Management", "Invariants"],
        "prerequisites": ["Class syntax", "Methods", "Attributes"],
        "description": "Implement a `BoundedCounter` class that manages an integer counter bounded between `min_val` and `max_val` inclusive.\n\nThe class must support:\n- `increment()`: increases value by 1 if not exceeding `max_val`\n- `decrement()`: decreases value by 1 if not less than `min_val`\n- `get_value()`: returns current integer value\n- `reset()`: sets value back to initial `min_val`",
        "input_format": "Class constructor arguments `min_val`, `max_val`.",
        "output_format": "Outputs of counter operations.",
        "examples": [
            {
                "input": "c = BoundedCounter(0, 2); c.increment(); c.increment(); c.increment(); c.get_value()",
                "output": "2",
                "explanation": "Counter increments to 2 and does not exceed maximum limit of 2."
            }
        ],
        "constraints": [
            "-10^4 <= min_val <= max_val <= 10^4"
        ],
        "starter_code": {
            "python": "class BoundedCounter:\n    def __init__(self, min_val: int, max_val: int):\n        pass\n\n    def increment(self) -> None:\n        pass\n\n    def decrement(self) -> None:\n        pass\n\n    def get_value(self) -> int:\n        pass\n\n    def reset(self) -> None:\n        pass\n"
        },
        "supported_languages": ["python", "cpp", "java", "javascript"]
    },
    {
        "id": "word-search-backtracking",
        "title": "Grid Word Search Backtracking",
        "source": "CodeMind Original",
        "source_url": "https://codemind.dev/problems/word-search-backtracking",
        "external_id": "CM-019",
        "problem_type": "Interview",
        "difficulty": "Medium",
        "rating": None,
        "domains": ["Backtracking", "DFS", "Arrays"],
        "tags": ["backtracking", "matrix", "dfs"],
        "concepts": ["State Exploration", "Cell Marking / Unmarking"],
        "prerequisites": ["Recursion", "2D Grid coordinates"],
        "description": "Given an `m x n` grid of characters `board` and a string `word`, return `True` if `word` exists in the grid.\n\nThe word can be constructed from letters of sequentially adjacent cells, where adjacent cells are horizontally or vertically neighboring. The same letter cell may not be used more than once.",
        "input_format": "2D character array `board` and a string `word`.",
        "output_format": "Boolean `True` or `False`.",
        "examples": [
            {
                "input": "board = [[\"A\",\"B\",\"C\",\"E\"],[\"S\",\"F\",\"C\",\"S\"],[\"A\",\"D\",\"E\",\"E\"]], word = \"ABCCED\"",
                "output": "True",
                "explanation": "Path A -> B -> C -> C -> E -> D exists."
            }
        ],
        "constraints": [
            "m == board.length",
            "n = board[i].length",
            "1 <= m, n <= 6",
            "1 <= word.length <= 15"
        ],
        "starter_code": {
            "python": "def exist(board: list[list[str]], word: str) -> bool:\n    # Write your solution here\n    pass\n"
        },
        "supported_languages": ["python", "cpp", "java"]
    }
]
