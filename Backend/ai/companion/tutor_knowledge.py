"""
CodeMind AI Tutor Pedagogical Knowledge Base
Comprehensive CS lessons, structured revision notes, language patterns, and comparisons.
"""

from typing import Dict, Any, List, Optional

TOPIC_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "Recursion": {
        "display_name": "Recursion",
        "definition": "Recursion is a computational problem-solving technique where a function solves a problem by calling a smaller instance of itself until it reaches a fundamental stopping condition known as the base case.",
        "analogy": "Think of recursion like Russian nesting dolls (Matryoshka dolls): you keep opening smaller and smaller dolls until you hit the solid core doll (the base case), at which point you assemble each doll back together on the way out.",
        "why_needed": "Recursion elegantly simplifies problems that exhibit self-similar subproblem structures—such as traversing tree hierarchies, exploring graph mazes (DFS), divide-and-conquer sorting (Mergesort/Quicksort), and backtracking.",
        "how_it_works": (
            "1. **Base Case Check**: The function immediately evaluates whether the simplest termination condition is reached. If so, it returns an explicit value without making another recursive call.\n"
            "2. **Recursive Decomposition**: If the base case is not met, the function decomposes the input into one or more strictly smaller subproblems and calls itself.\n"
            "3. **Call Stack Unwinding**: Each recursive call pushes an isolated stack frame onto the system Call Stack with its own local variables. Once a leaf base case returns, stack frames pop in reverse (LIFO) order, propagating return values up to the original caller."
        ),
        "syntax": {
            "python": (
                "def factorial(n: int) -> int:\n"
                "    # 1. Base Case: stop condition\n"
                "    if n <= 1:\n"
                "        return 1\n"
                "    # 2. Recursive Step: smaller subproblem\n"
                "    return n * factorial(n - 1)\n\n"
                "# Example call: factorial(4) -> 24"
            ),
            "c": (
                "#include <stdio.h>\n\n"
                "int factorial(int n) {\n"
                "    // 1. Base Case: stops infinite recursion\n"
                "    if (n <= 1) return 1;\n"
                "    // 2. Recursive Step: call self with (n - 1)\n"
                "    return n * factorial(n - 1);\n"
                "}\n\n"
                "int main() {\n"
                "    printf(\"factorial(4) = %d\\n\", factorial(4)); // 24\n"
                "    return 0;\n"
                "}"
            ),
            "cpp": (
                "#include <iostream>\n\n"
                "long long factorial(int n) {\n"
                "    if (n <= 1) return 1; // Base case\n"
                "    return n * factorial(n - 1); // Recursive step\n"
                "}\n\n"
                "int main() {\n"
                "    std::cout << \"4! = \" << factorial(4) << \"\\n\";\n"
                "    return 0;\n"
                "}"
            ),
            "java": (
                "public class RecursionDemo {\n"
                "    public static int factorial(int n) {\n"
                "        if (n <= 1) return 1; // Base case\n"
                "        return n * factorial(n - 1); // Recursive step\n"
                "    }\n"
                "    public static void main(String[] args) {\n"
                "        System.out.println(factorial(4)); // 24\n"
                "    }\n"
                "}"
            ),
            "javascript": (
                "function factorial(n) {\n"
                "    if (n <= 1) return 1; // Base case\n"
                "    return n * factorial(n - 1); // Recursive step\n"
                "}\n"
                "console.log(factorial(4)); // 24"
            )
        },
        "walkthrough": (
            "Let's trace `factorial(3)` on the system Call Stack:\n"
            "- Step 1: `factorial(3)` calls `factorial(2)` (Stack depth: 1)\n"
            "- Step 2: `factorial(2)` calls `factorial(1)` (Stack depth: 2)\n"
            "- Step 3: `factorial(1)` encounters `n <= 1`, returning `1` directly without further calls! (Base case triggered)\n"
            "- Step 4: `factorial(2)` receives `1`, computes `2 * 1 = 2`, and returns `2`.\n"
            "- Step 5: `factorial(3)` receives `2`, computes `3 * 2 = 6`, and returns `6`."
        ),
        "when_to_use": "Hierarchical structures (binary trees, ASTs, file systems), backtracking search (permutations, N-Queens, Sudoku), divide-and-conquer algorithms (Mergesort, Quicksort).",
        "when_not_to_use": "Simple linear traversals or counters where a single `for`/`while` loop uses O(1) auxiliary memory instead of O(N) stack frames.",
        "pitfalls": "1. Forgetting or miswriting the base case leading to `RecursionError: maximum recursion depth exceeded` or Stack Overflow.\n2. Failing to advance arguments strictly toward the base case.\n3. Recalculating identical subproblems without memoization (e.g. naive recursive Fibonacci is O(2^N)).",
        "practice_challenge": "Write a recursive function `sum_digits(n)` that takes a positive integer (e.g., `1234`) and returns the sum of its digits (`1 + 2 + 3 + 4 = 10`). Identify the base case before coding!",
        "notes": {
            "summary": "Recursion decomposes a problem into identical smaller instances. Every valid recursion requires at least one Base Case to terminate and a Recursive Step that strictly converges toward that base case.",
            "key_terms": [
                "**Base Case**: The conditional check where the function returns directly without recurring.",
                "**Call Stack**: The runtime data structure storing active stack frames, parameters, and return addresses.",
                "**Stack Overflow**: Memory exhaustion caused when recursion recurs indefinitely without reaching a base case.",
                "**Tail Recursion**: A recursive call positioned as the final operation, which compilers can optimize to O(1) space."
            ],
            "formulas": (
                "- **Time Complexity**: Often analyzed via recurrence relations using the Master Theorem: T(N) = a*T(N/b) + f(N)\n"
                "- **Space Complexity**: Proportional to maximum recursion depth: O(H) where H is the height of the call tree."
            ),
            "cheat_sheet": [
                {"Aspect": "Primary Requirement", "Detail": "Base Case + Converging Step"},
                {"Aspect": "Space Overhead", "Detail": "O(depth) on Call Stack"},
                {"Aspect": "Failure Mode", "Detail": "Stack Overflow / RecursionError"},
                {"Aspect": "Canonical Fix for Duplicates", "Detail": "Memoization (Top-Down DP)"}
            ]
        },
        "quiz": {
            "question": "What happens if a recursive function does not have a properly reachable base case?",
            "options": [
                "A) The compiler replaces it with an iterative loop.",
                "B) It runs until call-stack memory is exhausted, throwing a Stack Overflow.",
                "C) It automatically returns null after 1000 iterations.",
                "D) The function pauses execution and prompts the user."
            ],
            "correct_key": "B",
            "explanation": "Without a valid base case, each call allocates a new stack frame on the call stack until memory limit is exceeded, triggering a Stack Overflow."
        }
    },

    "Pointers": {
        "display_name": "Pointers in C",
        "definition": "A pointer in C is a variable that stores the memory address of another variable, rather than holding a direct data value.",
        "analogy": "Think of a pointer like a slip of paper with a friend's physical street address written on it: the paper itself is not the house, but it provides the exact coordinates to find, enter, or renovate that house.",
        "why_needed": (
            "1. **Pass-by-Reference**: C passes function arguments by value. Pointers allow functions to mutate caller variables.\n"
            "2. **Dynamic Memory Allocation**: Requesting heap memory via `malloc()`, `calloc()`, and `realloc()` returns raw pointers.\n"
            "3. **Dynamic Data Structures**: Building linked lists, binary trees, graphs, and dynamic sets requires node pointer connections.\n"
            "4. **Performance**: Passing a pointer to a large `struct` costs 4 or 8 bytes, avoiding copying massive memory blocks."
        ),
        "how_it_works": (
            "1. **Address-of Operator (`&`)**: Obtains the hexadecimal memory address where a variable is stored.\n"
            "2. **Pointer Declaration (`*`)**: Declares a pointer typed to point to a specific variable type (e.g. `int *ptr`).\n"
            "3. **Dereference Operator (`*`)**: Accesses or overwrites the actual data value stored at the address pointed to."
        ),
        "syntax": {
            "c": (
                "#include <stdio.h>\n\n"
                "void addBonus(int *scorePtr) {\n"
                "    *scorePtr += 10; // Dereference to mutate caller's variable\n"
                "}\n\n"
                "int main() {\n"
                "    int score = 85;\n"
                "    int *ptr = &score; // '&' gets address, ptr points to score\n\n"
                "    printf(\"Value of score:         %d\\n\", score);     // 85\n"
                "    printf(\"Memory Address of score: %p\\n\", (void*)ptr); // e.g. 0x7ffd98\n"
                "    printf(\"Dereferenced via ptr:    %d\\n\", *ptr);     // 85\n\n"
                "    *ptr = 90; // Overwrite value through pointer\n"
                "    printf(\"Updated score:          %d\\n\", score);     // 90\n\n"
                "    addBonus(&score); // Pass address to function\n"
                "    printf(\"After function call:    %d\\n\", score);     // 100\n"
                "    return 0;\n"
                "}"
            ),
            "cpp": (
                "#include <iostream>\n\n"
                "int main() {\n"
                "    int val = 42;\n"
                "    int* ptr = &val;\n"
                "    std::cout << \"Address: \" << ptr << \" | Value: \" << *ptr << \"\\n\";\n"
                "    *ptr = 99;\n"
                "    std::cout << \"Modified val: \" << val << \"\\n\";\n"
                "    return 0;\n"
                "}"
            ),
            "python": (
                "# Python uses object references rather than direct memory pointers:\n"
                "a = [1, 2, 3]\n"
                "b = a  # 'b' references the exact same list in memory\n"
                "b.append(4)\n"
                "print(a)  # [1, 2, 3, 4] -- mutations reflect in 'a'!"
            ),
            "java": (
                "// Java handles references automatically under the hood:\n"
                "class Node {\n"
                "    int val;\n"
                "    Node next; // Reference to another Node object\n"
                "    Node(int v) { this.val = v; }\n"
                "}"
            ),
            "javascript": (
                "// JavaScript uses reference semantics for objects:\n"
                "let objA = { val: 10 };\n"
                "let objB = objA; // Both point to same object\n"
                "objB.val = 25;\n"
                "console.log(objA.val); // 25"
            )
        },
        "walkthrough": (
            "Step-by-step memory model in C:\n"
            "```\n"
            "Variable: score                Pointer: ptr\n"
            "Address:  0x7ffd98             Address:  0x7ffd90\n"
            "Value:    [ 85 ] <───────────── Value:    [ 0x7ffd98 ]\n"
            "```\n"
            "1. When `int *ptr = &score;` executes, `ptr` stores the memory address `0x7ffd98`.\n"
            "2. Evaluating `*ptr` tells the CPU: go to address `0x7ffd98` and read the integer stored there (85).\n"
            "3. Writing `*ptr = 90;` tells the CPU: overwrite address `0x7ffd98` with 90, directly changing `score`."
        ),
        "when_to_use": "Direct memory manipulation, pass-by-reference in C functions, dynamic memory management (`malloc`/`free`), and constructing node-based data structures (Linked Lists, Trees).",
        "when_not_to_use": "Avoid pointer arithmetic when simple array indexing `arr[i]` is sufficient and less error-prone.",
        "pitfalls": (
            "1. **Dereferencing NULL or Uninitialized Pointers**: Triggers an instant `Segmentation Fault (core dumped)`.\n"
            "2. **Dangling Pointers**: Accessing a pointer after the memory it points to has been `free()`d or gone out of scope.\n"
            "3. **Memory Leaks**: Allocating heap memory with `malloc()` without pairing with a matching `free()`.\n"
            "4. **Buffer Overflows**: Incrementing a pointer past allocated bounds."
        ),
        "practice_challenge": "Write a C function `void swap(int *a, int *b)` that swaps the values of two integers using pointers without returning anything.",
        "notes": {
            "summary": "Pointers hold memory addresses. Use `&` (address-of) to grab an address, and `*` (dereference) to read or modify the underlying value.",
            "key_terms": [
                "**Address-of (`&`)**: Unary operator that returns the memory location of an lvalue.",
                "**Dereference (`*`)**: Unary operator that accesses the value stored at the referenced address.",
                "**NULL Pointer**: A pointer with address value 0, indicating it points to nothing valid.",
                "**Dangling Pointer**: A pointer still holding an address to deallocated or freed memory."
            ],
            "formulas": (
                "- Address calculation: `ptr + i` advances by `i * sizeof(*ptr)` bytes.\n"
                "- Pointer size: 4 bytes on 32-bit OS, 8 bytes on 64-bit OS."
            ),
            "cheat_sheet": [
                {"Syntax": "int *p = &x;", "Meaning": "Declare pointer 'p' holding address of 'x'"},
                {"Syntax": "*p = 50;", "Meaning": "Write 50 into the memory location stored in 'p'"},
                {"Syntax": "int y = *p;", "Meaning": "Read value from memory location stored in 'p'"},
                {"Syntax": "p = NULL;", "Meaning": "Safely invalidate pointer after free()"}
            ]
        },
        "quiz": {
            "question": "What happens when you execute `*ptr = 100;` if `int *ptr = NULL;` in C?",
            "options": [
                "A) The integer 100 is printed to standard output.",
                "B) The variable ptr is assigned address 100.",
                "C) A Segmentation Fault occurs because address 0 is protected.",
                "D) The operating system allocates an emergency 4-byte buffer."
            ],
            "correct_key": "C",
            "explanation": "Dereferencing NULL attempts to write to address 0, which triggers a hardware protection fault (Segmentation Fault)."
        }
    },

    "Binary Search": {
        "display_name": "Binary Search",
        "definition": "Binary Search is an optimal O(log N) divide-and-conquer search algorithm that locates the position of a target value within a sorted collection by repeatedly halving the active search interval.",
        "analogy": "Think of guessing a secret number between 1 and 100: you guess 50, and if told 'Higher', you immediately discard the entire bottom half (1–50) in a single step.",
        "why_needed": "Linear search requires O(N) comparisons—checking 1,000,000 items sequentially takes up to 1,000,000 checks. Binary search solves the exact same problem in at most 20 comparisons (log2(1,000,000) ≈ 20).",
        "how_it_works": (
            "1. **Initialize Bounds**: Set `low = 0` and `high = N - 1`.\n"
            "2. **Find Middle**: Compute `mid = low + (high - low) // 2` to safely avoid integer overflow.\n"
            "3. **Evaluate Invariant**:\n"
            "   - If `nums[mid] == target`, target is found at index `mid`.\n"
            "   - If `nums[mid] < target`, discard the left half by setting `low = mid + 1`.\n"
            "   - If `nums[mid] > target`, discard the right half by setting `high = mid - 1`.\n"
            "4. **Termination**: Repeat while `low <= high`. If `low > high`, the target does not exist in the array."
        ),
        "syntax": {
            "python": (
                "def binary_search(nums: list[int], target: int) -> int:\n"
                "    low, high = 0, len(nums) - 1\n"
                "    while low <= high:\n"
                "        mid = low + (high - low) // 2\n"
                "        if nums[mid] == target:\n"
                "            return mid\n"
                "        elif nums[mid] < target:\n"
                "            low = mid + 1\n"
                "        else:\n"
                "            high = mid - 1\n"
                "    return -1"
            ),
            "c": (
                "#include <stdio.h>\n\n"
                "int binarySearch(int arr[], int size, int target) {\n"
                "    int low = 0, high = size - 1;\n"
                "    while (low <= high) {\n"
                "        int mid = low + (high - low) / 2; // Prevents 32-bit int overflow\n"
                "        if (arr[mid] == target) return mid;\n"
                "        else if (arr[mid] < target) low = mid + 1;\n"
                "        else high = mid - 1;\n"
                "    }\n"
                "    return -1;\n"
                "}"
            ),
            "cpp": (
                "#include <vector>\n\n"
                "int binarySearch(const std::vector<int>& nums, int target) {\n"
                "    int low = 0, high = nums.size() - 1;\n"
                "    while (low <= high) {\n"
                "        int mid = low + (high - low) / 2;\n"
                "        if (nums[mid] == target) return mid;\n"
                "        else if (nums[mid] < target) low = mid + 1;\n"
                "        else high = mid - 1;\n"
                "    }\n"
                "    return -1;\n"
                "}"
            ),
            "java": (
                "public class BinarySearch {\n"
                "    public static int search(int[] nums, int target) {\n"
                "        int low = 0, high = nums.length - 1;\n"
                "        while (low <= high) {\n"
                "            int mid = low + (high - low) / 2;\n"
                "            if (nums[mid] == target) return mid;\n"
                "            else if (nums[mid] < target) low = mid + 1;\n"
                "            else high = mid - 1;\n"
                "        }\n"
                "        return -1;\n"
                "    }\n"
                "}"
            ),
            "javascript": (
                "function binarySearch(nums, target) {\n"
                "    let low = 0, high = nums.length - 1;\n"
                "    while (low <= high) {\n"
                "        const mid = Math.floor(low + (high - low) / 2);\n"
                "        if (nums[mid] === target) return mid;\n"
                "        else if (nums[mid] < target) low = mid + 1;\n"
                "        else high = mid - 1;\n"
                "    }\n"
                "    return -1;\n"
                "}"
            )
        },
        "walkthrough": (
            "Searching `target = 7` in sorted array `[1, 3, 5, 7, 9, 11]`:\n"
            "- Step 1: `low = 0`, `high = 5` -> `mid = 2` (`nums[2] = 5`). Since `5 < 7`, search space shifts right: `low = 3`.\n"
            "- Step 2: `low = 3`, `high = 5` -> `mid = 4` (`nums[4] = 9`). Since `9 > 7`, search space shifts left: `high = 3`.\n"
            "- Step 3: `low = 3`, `high = 3` -> `mid = 3` (`nums[3] = 7`). Match found! Returns index `3`."
        ),
        "when_to_use": "Any lookup over sorted arrays, or 'Binary Search on Answer' when an evaluation predicate is monotonic (e.g. finding minimum capacity to ship packages).",
        "when_not_to_use": "Unsorted data (sorting takes O(N log N)), or Linked Lists (no O(1) direct index access to calculate `mid`).",
        "pitfalls": (
            "1. **Integer Overflow**: Writing `(low + high) / 2` can overflow 32-bit signed integers when `low + high > 2^31 - 1`. Always write `low + (high - low) / 2`.\n"
            "2. **Off-by-One Loop Condition**: Using `low < high` instead of `low <= high` can miss the single-element candidate.\n"
            "3. **Infinite Loops**: Setting `low = mid` or `high = mid` without `+ 1` / `- 1` when window size is 2."
        ),
        "practice_challenge": "Given a sorted array of integers that may contain duplicates, modify binary search to find the *first* occurrence index of `target`.",
        "notes": {
            "summary": "Binary search halves the search space each step on sorted/monotonic inputs, delivering O(log N) time and O(1) space.",
            "key_terms": [
                "**Monotonicity**: The prerequisite property where values (or condition truth values) are sorted non-decreasingly.",
                "**Search Space**: The range `[low, high]` containing potential valid candidate answers.",
                "**Safe Midpoint**: `low + (high - low) // 2` to prevent numeric overflow.",
                "**Binary Search on Answer**: Transforming an optimization problem into a feasibility check over a bounded range."
            ],
            "formulas": (
                "- **Time Complexity**: Best: O(1), Average: O(log N), Worst: O(log N)\n"
                "- **Space Complexity**: O(1) iterative, O(log N) recursive."
            ),
            "cheat_sheet": [
                {"Metric": "Best Time", "Value": "O(1)"},
                {"Metric": "Average Time", "Value": "O(log N)"},
                {"Metric": "Worst Time", "Value": "O(log N)"},
                {"Metric": "Auxiliary Space", "Value": "O(1) Iterative"},
                {"Metric": "Prerequisite", "Value": "Sorted / Monotonic Array"}
            ]
        },
        "quiz": {
            "question": "Why is `mid = low + (high - low) / 2` preferred over `mid = (low + high) / 2` in C/C++/Java?",
            "options": [
                "A) It executes faster on GPU hardware.",
                "B) It prevents 32-bit signed integer overflow when low + high exceeds 2,147,483,647.",
                "C) It automatically rounds toward zero for negative numbers.",
                "D) It allows binary searching over floating point values."
            ],
            "correct_key": "B",
            "explanation": "If low and high are large (e.g. > 1 billion), their sum exceeds 2^31 - 1 and wraps around to a negative number, causing an index out of bounds error."
        }
    },

    "Stack": {
        "display_name": "Stack Data Structure",
        "definition": "A Stack is a linear data structure that adheres strictly to the Last-In, First-Out (LIFO) principle. All element insertions (push) and deletions (pop) occur exclusively at the top of the stack.",
        "analogy": "Think of a spring-loaded cafeteria plate dispenser: the last clean plate placed onto the top is always the very first plate picked up by a customer.",
        "why_needed": "Essential for tracking nested structures (parentheses matching, HTML tag validation), runtime execution management (call stack frames), undo/redo action buffers, and monotonic stack optimizations.",
        "how_it_works": (
            "- `push(val)`: Places a new element on top of the stack in O(1) time.\n"
            "- `pop()`: Removes and returns the top element in O(1) time.\n"
            "- `peek()` / `top()`: Inspects the top element without removing it in O(1) time.\n"
            "- `isEmpty()`: Verifies whether the stack contains any items."
        ),
        "syntax": {
            "python": (
                "stack = []\n"
                "stack.append(10)  # Push O(1)\n"
                "stack.append(20)\n"
                "top_val = stack[-1] # Peek O(1) -> 20\n"
                "popped = stack.pop() # Pop O(1) -> 20"
            ),
            "c": (
                "#define MAX 100\n"
                "int stack[MAX];\n"
                "int top = -1;\n\n"
                "void push(int v) { if (top < MAX - 1) stack[++top] = v; }\n"
                "int pop() { return (top >= 0) ? stack[top--] : -1; }\n"
                "int peek() { return (top >= 0) ? stack[top] : -1; }"
            ),
            "cpp": (
                "#include <stack>\n"
                "std::stack<int> s;\n"
                "s.push(10);        // Push O(1)\n"
                "int top = s.top(); // Peek O(1)\n"
                "s.pop();           // Pop O(1)"
            ),
            "java": (
                "import java.util.ArrayDeque;\n"
                "import java.util.Deque;\n\n"
                "Deque<Integer> stack = new ArrayDeque<>();\n"
                "stack.push(10);        // Push O(1)\n"
                "int top = stack.peek();// Peek O(1)\n"
                "int pop = stack.pop(); // Pop O(1)"
            ),
            "javascript": (
                "const stack = [];\n"
                "stack.push(10);               // Push\n"
                "const top = stack[stack.length - 1]; // Peek\n"
                "const popped = stack.pop();   // Pop"
            )
        },
        "walkthrough": "Pushing 10, then 20, then 30: Stack is `[10, 20, 30]` with TOP at 30. `pop()` returns 30, leaving `[10, 20]` with TOP at 20.",
        "when_to_use": "Parentheses/bracket syntax verification, expression evaluation (Reverse Polish Notation), DFS graph traversal, monotonic next greater element.",
        "when_not_to_use": "When elements must be processed in the exact order they arrived (FIFO—use a Queue instead).",
        "pitfalls": "Popping from an empty stack (IndexError or stack underflow); unbounded growth leading to out-of-memory.",
        "practice_challenge": "Given a string containing only characters '(', ')', '{', '}', '[', ']', use a stack to determine if the input string has valid matching parentheses.",
        "notes": {
            "summary": "LIFO linear structure. Push, pop, and peek operate in constant O(1) time.",
            "key_terms": [
                "**LIFO**: Last-In, First-Out access order.",
                "**Underflow**: Attempting to pop or peek from an empty stack.",
                "**Overflow**: Exceeding the maximum static capacity of an array-backed stack."
            ],
            "formulas": "All primary operations (Push, Pop, Peek) run in O(1) amortized time.",
            "cheat_sheet": [
                {"Operation": "push(x)", "Time": "O(1)"},
                {"Operation": "pop()", "Time": "O(1)"},
                {"Operation": "peek()", "Time": "O(1)"}
            ]
        },
        "quiz": {
            "question": "Which algorithmic technique naturally utilizes a Stack to manage active frames?",
            "options": ["A) Breadth-First Search (BFS)", "B) Recursion / Depth-First Search (DFS)", "C) Binary Search", "D) Radix Sort"],
            "correct_key": "B",
            "explanation": "Recursion manages function execution frames using the system Call Stack, which behaves identically to a LIFO stack."
        }
    },

    "Queue": {
        "display_name": "Queue Data Structure",
        "definition": "A Queue is a linear data structure that strictly adheres to the First-In, First-Out (FIFO) principle. Elements are inserted at the rear (enqueue) and removed from the front (dequeue).",
        "analogy": "Think of people waiting in line at a movie theater ticket counter: the first person to arrive and join the line is the first person served and allowed into the theater.",
        "why_needed": "Crucial for Breadth-First Search (BFS) level-order exploration, asynchronous job spooling, CPU task scheduling, and real-time streaming buffers.",
        "how_it_works": (
            "- `enqueue(val)`: Inserts element at the rear in O(1) time.\n"
            "- `dequeue()`: Removes element from the front in O(1) time.\n"
            "- `front()`: Peeks at the next element to be processed without removing it."
        ),
        "syntax": {
            "python": (
                "from collections import deque\n"
                "q = deque()\n"
                "q.append(10)       # Enqueue O(1)\n"
                "q.append(20)\n"
                "front = q[0]       # Front O(1) -> 10\n"
                "dequeued = q.popleft() # Dequeue O(1) -> 10"
            ),
            "c": (
                "#define MAX 100\n"
                "int q[MAX], front = 0, rear = 0;\n"
                "void enqueue(int v) { q[rear++] = v; }\n"
                "int dequeue() { return q[front++]; }"
            ),
            "cpp": (
                "#include <queue>\n"
                "std::queue<int> q;\n"
                "q.push(10);        // Enqueue O(1)\n"
                "int f = q.front(); // Front O(1)\n"
                "q.pop();           // Dequeue O(1)"
            ),
            "java": (
                "import java.util.LinkedList;\n"
                "import java.util.Queue;\n\n"
                "Queue<Integer> q = new LinkedList<>();\n"
                "q.offer(10);       // Enqueue O(1)\n"
                "int f = q.peek();  // Front O(1)\n"
                "int out = q.poll();// Dequeue O(1)"
            ),
            "javascript": (
                "const q = [];\n"
                "q.push(10);        // Enqueue\n"
                "const f = q[0];    // Front\n"
                "const val = q.shift(); // Dequeue"
            )
        },
        "walkthrough": "Enqueue 10, then 20, then 30: Queue is `[10, 20, 30]` with FRONT at 10 and REAR at 30. `dequeue()` removes 10, leaving `[20, 30]` with FRONT at 20.",
        "when_to_use": "BFS tree/graph traversals, job scheduling, message queues, rate-limiting sliding window buffers.",
        "when_not_to_use": "When recent items must be accessed first (use a Stack). In Python, avoid `list.pop(0)` which is O(N); always use `collections.deque`.",
        "pitfalls": "Using `list.pop(0)` in Python which shifts all elements (O(N) operation instead of O(1)).",
        "practice_challenge": "Implement a level-order traversal of a binary tree using a Queue.",
        "notes": {
            "summary": "FIFO linear structure. Enqueue at rear, dequeue at front. Both operate in O(1) time.",
            "key_terms": [
                "**FIFO**: First-In, First-Out order.",
                "**Enqueue**: Appending to the rear.",
                "**Dequeue**: Removing from the front.",
                "**Circular Queue**: Wrapping array indices around modulo capacity to prevent memory drift."
            ],
            "formulas": "Enqueue: O(1), Dequeue: O(1), Space: O(N).",
            "cheat_sheet": [
                {"Operation": "enqueue(x)", "Time": "O(1)"},
                {"Operation": "dequeue()", "Time": "O(1)"},
                {"Operation": "front()", "Time": "O(1)"}
            ]
        },
        "quiz": {
            "question": "Which algorithm relies on a Queue to guarantee finding the shortest path in an unweighted graph?",
            "options": ["A) Depth-First Search (DFS)", "B) Breadth-First Search (BFS)", "C) Binary Search", "D) Quicksort"],
            "correct_key": "B",
            "explanation": "BFS explores nodes level by level using a FIFO queue, guaranteeing that vertices closest to the origin are visited first."
        }
    },

    "Linked List": {
        "display_name": "Linked List",
        "definition": "A Linked List is a dynamic linear data structure where elements (nodes) are stored non-contiguously in memory, each containing a data payload and a pointer/reference to the next node in the sequence.",
        "analogy": "Think of a treasure hunt: each clue card you find tells you a hint (data) and gives you the exact GPS location of the next clue card (pointer).",
        "why_needed": "Arrays require contiguous memory blocks and O(N) element shifting when inserting or deleting elements. Linked lists provide O(1) insertions and deletions anywhere once the target node pointer is available.",
        "how_it_works": (
            "1. **Node Structure**: Holds `val` (the payload) and `next` (a pointer to the subsequent node, or `NULL` at the tail).\n"
            "2. **Head Pointer**: Points to the first node in the sequence.\n"
            "3. **Insertion**: Rewires pointers: `new_node.next = current.next; current.next = new_node;` in O(1) time without shifting other nodes."
        ),
        "syntax": {
            "python": (
                "class ListNode:\n"
                "    def __init__(self, val=0, next=None):\n"
                "        self.val = val\n"
                "        self.next = next\n\n"
                "def print_list(head: ListNode):\n"
                "    curr = head\n"
                "    while curr:\n"
                "        print(curr.val, end=' -> ')\n"
                "        curr = curr.next\n"
                "    print('None')"
            ),
            "c": (
                "#include <stdio.h>\n"
                "#include <stdlib.h>\n\n"
                "struct Node {\n"
                "    int val;\n"
                "    struct Node *next;\n"
                "};\n\n"
                "struct Node* insertAtHead(struct Node *head, int val) {\n"
                "    struct Node *newNode = (struct Node*)malloc(sizeof(struct Node));\n"
                "    newNode->val = val;\n"
                "    newNode->next = head;\n"
                "    return newNode;\n"
                "}"
            ),
            "cpp": (
                "struct ListNode {\n"
                "    int val;\n"
                "    ListNode *next;\n"
                "    ListNode(int x) : val(x), next(nullptr) {}\n"
                "};"
            ),
            "java": (
                "public class ListNode {\n"
                "    int val;\n"
                "    ListNode next;\n"
                "    ListNode(int val) { this.val = val; }\n"
                "}"
            ),
            "javascript": (
                "class ListNode {\n"
                "    constructor(val, next = null) {\n"
                "        this.val = val;\n"
                "        this.next = next;\n"
                "    }\n"
                "}"
            )
        },
        "walkthrough": "To insert 5 at head of `10 -> 20 -> None`: Create node 5, set `5.next = head` (`10`), update `head = 5`. Result: `5 -> 10 -> 20 -> None`.",
        "when_to_use": "Frequent insertions/deletions at beginning or middle, dynamic sizing where total count is unknown ahead of time.",
        "when_not_to_use": "When frequent random index access `arr[i]` is required (lists require O(N) traversal), or cache locality is critical.",
        "pitfalls": "Losing the head pointer; dereferencing `NULL` on tail traversal (`curr.next.val` when `curr.next` is `NULL`).",
        "practice_challenge": "Write an algorithm to reverse a singly linked list in-place in O(N) time and O(1) space.",
        "notes": {
            "summary": "Node-based dynamic data structure with O(1) insertions/deletions and O(N) sequential search.",
            "key_terms": [
                "**Head**: Pointer to the first node.",
                "**Tail**: The last node whose `next` is `NULL`.",
                "**Dummy Node**: An artificial sentinel head node used to simplify edge-case insertions/deletions.",
                "**Fast & Slow Pointers**: Technique for cycle detection (Floyd's algorithm) and finding midpoints."
            ],
            "formulas": "Access: O(N), Search: O(N), Insert at head: O(1), Delete at head: O(1).",
            "cheat_sheet": [
                {"Operation": "Insert at Head", "Time": "O(1)"},
                {"Operation": "Delete at Head", "Time": "O(1)"},
                {"Operation": "Search by Value", "Time": "O(N)"},
                {"Operation": "Random Access by Index", "Time": "O(N)"}
            ]
        },
        "quiz": {
            "question": "What is the primary advantage of a Singly Linked List over a standard dynamic Array?",
            "options": [
                "A) Instant O(1) random index access.",
                "B) Constant time O(1) element insertion at the head without shifting remaining elements.",
                "C) Better CPU cache memory locality.",
                "D) Zero memory overhead for pointers."
            ],
            "correct_key": "B",
            "explanation": "Inserting at index 0 of an array requires shifting all N elements. A linked list simply rewires two pointers in O(1) time."
        }
    },

    "Sorting": {
        "display_name": "Sorting Algorithms (Quicksort & Mergesort)",
        "definition": "Sorting is the algorithmic process of arranging data elements into a specified monotonic order (e.g. ascending or descending).",
        "analogy": "Think of organizing a scattered hand of playing cards: you pick cards one by one and place smaller cards to the left of larger cards.",
        "why_needed": "Sorted data unlocks logarithmic O(log N) binary searches, enables two-pointer linear scans, removes duplicates efficiently, and forms the bedrock of database query execution.",
        "how_it_works": (
            "**Quicksort (Divide & Conquer)**:\n"
            "1. Choose a **pivot** element from the array.\n"
            "2. **Partition**: Rearrange the array so elements `< pivot` move left, and elements `> pivot` move right.\n"
            "3. **Recurse**: Recursively apply Quicksort to left and right subarrays.\n\n"
            "**Mergesort (Stable Divide & Conquer)**:\n"
            "1. Divide the array into two equal halves.\n"
            "2. Recursively sort both halves.\n"
            "3. Merge the two sorted halves in O(N) linear time."
        ),
        "syntax": {
            "python": (
                "def quicksort(nums: list[int]) -> list[int]:\n"
                "    if len(nums) <= 1:\n"
                "        return nums\n"
                "    pivot = nums[len(nums) // 2]\n"
                "    left = [x for x in nums if x < pivot]\n"
                "    middle = [x for x in nums if x == pivot]\n"
                "    right = [x for x in nums if x > pivot]\n"
                "    return quicksort(left) + middle + quicksort(right)"
            ),
            "c": (
                "#include <stdio.h>\n\n"
                "void swap(int *a, int *b) { int t = *a; *a = *b; *b = t; }\n\n"
                "int partition(int arr[], int low, int high) {\n"
                "    int pivot = arr[high];\n"
                "    int i = low - 1;\n"
                "    for (int j = low; j < high; j++) {\n"
                "        if (arr[j] < pivot) { i++; swap(&arr[i], &arr[j]); }\n"
                "    }\n"
                "    swap(&arr[i + 1], &arr[high]);\n"
                "    return i + 1;\n"
                "}\n\n"
                "void quicksort(int arr[], int low, int high) {\n"
                "    if (low < high) {\n"
                "        int pi = partition(arr, low, high);\n"
                "        quicksort(arr, low, pi - 1);\n"
                "        quicksort(arr, pi + 1, high);\n"
                "    }\n"
                "}"
            ),
            "cpp": (
                "#include <algorithm>\n"
                "#include <vector>\n\n"
                "void sortVector(std::vector<int>& nums) {\n"
                "    std::sort(nums.begin(), nums.end()); // Average O(N log N)\n"
                "}"
            ),
            "java": (
                "import java.util.Arrays;\n\n"
                "public class SortDemo {\n"
                "    public static void sortArray(int[] nums) {\n"
                "        Arrays.sort(nums); // Dual-pivot Quicksort O(N log N)\n"
                "    }\n"
                "}"
            ),
            "javascript": (
                "const nums = [5, 2, 9, 1, 5, 6];\n"
                "nums.sort((a, b) => a - b);\n"
                "console.log(nums); // [1, 2, 5, 5, 6, 9]"
            )
        },
        "walkthrough": (
            "Quicksort on `[7, 2, 1, 6, 8, 5]`, pivot = 5:\n"
            "- Left partition (`< 5`): `[2, 1]`\n"
            "- Pivot: `[5]`\n"
            "- Right partition (`> 5`): `[7, 6, 8]`\n"
            "- Recursively sort `[2, 1]` -> `[1, 2]`\n"
            "- Recursively sort `[7, 6, 8]` -> `[6, 7, 8]`\n"
            "- Concatenate: `[1, 2] + [5] + [6, 7, 8] = [1, 2, 5, 6, 7, 8]`."
        ),
        "when_to_use": "Quicksort for in-place cache-friendly general sorting; Mergesort when stability is needed or sorting linked lists.",
        "when_not_to_use": "When data is already sorted and naive pivot selection is used (degrades to O(N^2)).",
        "pitfalls": "Worst-case O(N^2) in Quicksort if pivot is always the maximum or minimum element. (Solved by randomized pivot or Median-of-Three).",
        "practice_challenge": "Explain how Mergesort achieves guaranteed O(N log N) worst-case time, and what memory trade-off it requires.",
        "notes": {
            "summary": "Comparison sorting lower bound is O(N log N). Quicksort is in-place and fastest on average; Mergesort is stable with O(N) space.",
            "key_terms": [
                "**Pivot**: Element chosen to partition arrays in Quicksort.",
                "**Stability**: Preserving the relative order of duplicate elements.",
                "**In-Place**: Algorithms requiring O(1) or O(log N) auxiliary memory."
            ],
            "formulas": "- Average Time: O(N log N)\n- Quicksort Worst: O(N^2)\n- Mergesort Worst: O(N log N)\n- Space: Quicksort O(log N), Mergesort O(N).",
            "cheat_sheet": [
                {"Algorithm": "Quicksort", "Avg Time": "O(N log N)", "Worst Time": "O(N^2)", "Space": "O(log N)", "Stable": "No"},
                {"Algorithm": "Mergesort", "Avg Time": "O(N log N)", "Worst Time": "O(N log N)", "Space": "O(N)", "Stable": "Yes"},
                {"Algorithm": "Heap Sort", "Avg Time": "O(N log N)", "Worst Time": "O(N log N)", "Space": "O(1)", "Stable": "No"}
            ]
        },
        "quiz": {
            "question": "What is the worst-case time complexity of standard Quicksort when the array is already sorted and the pivot is always the last element?",
            "options": ["A) O(N log N)", "B) O(N)", "C) O(N^2)", "D) O(log N)"],
            "correct_key": "C",
            "explanation": "When already sorted and picking an extreme element as pivot, the partition splits into sizes (N-1) and 0 each step, causing N levels of recursion: N + (N-1) + ... + 1 = O(N^2)."
        }
    },

    "Trees": {
        "display_name": "Trees & Binary Search Trees (BST)",
        "definition": "A Tree is a non-linear hierarchical data structure consisting of nodes connected by edges. A Binary Search Tree (BST) maintains the key invariant: all nodes in the left subtree are smaller than the root, and all nodes in the right subtree are larger.",
        "analogy": "Think of an organization chart: the CEO is at the root, VP managers are child nodes, and individual contributors are leaf nodes.",
        "why_needed": "BSTs combine the O(1) flexibility of linked node insertions with the O(log N) search speed of sorted arrays.",
        "how_it_works": "In-order traversal (Left -> Root -> Right) on a BST visits nodes in strictly ascending sorted order.",
        "syntax": {
            "python": (
                "class TreeNode:\n"
                "    def __init__(self, val=0, left=None, right=None):\n"
                "        self.val = val\n"
                "        self.left = left\n"
                "        self.right = right\n\n"
                "def search_bst(root, target):\n"
                "    if not root or root.val == target:\n"
                "        return root\n"
                "    if target < root.val:\n"
                "        return search_bst(root.left, target)\n"
                "    return search_bst(root.right, target)"
            ),
            "c": (
                "struct TreeNode {\n"
                "    int val;\n"
                "    struct TreeNode *left;\n"
                "    struct TreeNode *right;\n"
                "};"
            ),
            "cpp": (
                "struct TreeNode {\n"
                "    int val;\n"
                "    TreeNode *left;\n"
                "    TreeNode *right;\n"
                "    TreeNode(int x) : val(x), left(nullptr), right(nullptr) {}\n"
                "};"
            ),
            "java": (
                "public class TreeNode {\n"
                "    int val;\n"
                "    TreeNode left, right;\n"
                "    TreeNode(int val) { this.val = val; }\n"
                "}"
            ),
            "javascript": (
                "class TreeNode {\n"
                "    constructor(val, left = null, right = null) {\n"
                "        this.val = val;\n"
                "        this.left = left;\n"
                "        this.right = right;\n"
                "    }\n"
                "}"
            )
        },
        "walkthrough": "Searching 4 in BST with root 5: 4 < 5 -> go left to node 3. 4 > 3 -> go right to node 4. Found in 2 steps!",
        "when_to_use": "Hierarchical data representation (DOM tree, JSON parsing, file systems), fast sorted range queries, priority queues (Binary Heaps).",
        "when_not_to_use": "When data is static and sequential array lookup suffices without pointer overhead.",
        "pitfalls": "Unbalanced BSTs degenerating into linked lists with O(N) worst-case time (fixed by AVL or Red-Black trees).",
        "practice_challenge": "Given the root of a binary tree, return the maximum depth (height) of the tree using recursion.",
        "notes": {
            "summary": "Hierarchical node structure. BST property: Left < Root < Right. Search/insert is O(H) where H is tree height.",
            "key_terms": [
                "**Root**: The top-level ancestor node with no incoming parent edges.",
                "**Leaf**: A terminal node with no children.",
                "**In-Order Traversal**: Left -> Root -> Right (produces sorted order in BST).",
                "**Height**: Number of edges on the longest root-to-leaf path."
            ],
            "formulas": "Balanced BST: Search O(log N), Insert O(log N). Skewed BST: Search O(N).",
            "cheat_sheet": [
                {"Traversal": "In-Order", "Order": "Left -> Root -> Right", "Note": "Sorted in BST"},
                {"Traversal": "Pre-Order", "Order": "Root -> Left -> Right", "Note": "Tree copying"},
                {"Traversal": "Post-Order", "Order": "Left -> Right -> Root", "Note": "Bottom-up deletion"}
            ]
        },
        "quiz": {
            "question": "Which traversal order on a Binary Search Tree (BST) processes elements in ascending numerical order?",
            "options": ["A) Pre-order", "B) In-order", "C) Post-order", "D) Level-order"],
            "correct_key": "B",
            "explanation": "In-order traversal visits the left subtree (smaller values), then root, then right subtree (larger values), naturally yielding sorted order."
        }
    },

    "Graphs": {
        "display_name": "Graphs (BFS & DFS)",
        "definition": "A Graph is a non-linear data structure consisting of a set of vertices (nodes) and edges connecting pairs of vertices. Edges may be directed/undirected and weighted/unweighted.",
        "analogy": "Think of a flight route map: cities are vertices, direct flights are edges, and BFS finds the route with the fewest flight transfers.",
        "why_needed": "Models real-world networks: social connections (friends of friends), GPS navigation, dependency resolution (topological sort), and web crawling.",
        "how_it_works": (
            "1. **Representation**: Adjacency List `graph = {u: [v1, v2]}` is space-efficient O(V + E).\n"
            "2. **BFS (Queue)**: Explores concentric neighbor rings level-by-level; guarantees shortest path on unweighted graphs.\n"
            "3. **DFS (Stack/Recursion)**: Explores deep along each path before backtracking; detects cycles and topological orders."
        ),
        "syntax": {
            "python": (
                "from collections import deque\n\n"
                "# BFS Shortest Path:\n"
                "def bfs_shortest_path(graph, start, target):\n"
                "    queue = deque([(start, 0)])\n"
                "    visited = {start}\n"
                "    while queue:\n"
                "        node, dist = queue.popleft()\n"
                "        if node == target:\n"
                "            return dist\n"
                "        for neighbor in graph.get(node, []):\n"
                "            if neighbor not in visited:\n"
                "                visited.add(neighbor)\n"
                "                queue.append((neighbor, dist + 1))\n"
                "    return -1"
            ),
            "c": (
                "// Adjacency matrix or linked adjacency list:\n"
                "#define MAX_V 100\n"
                "int adj[MAX_V][MAX_V];\n"
                "int visited[MAX_V];"
            ),
            "cpp": (
                "#include <vector>\n"
                "#include <queue>\n\n"
                "std::vector<std::vector<int>> adj;\n"
                "std::vector<bool> visited;"
            ),
            "java": (
                "import java.util.*;\n\n"
                "Map<Integer, List<Integer>> adj = new HashMap<>();\n"
                "Set<Integer> visited = new HashSet<>();"
            ),
            "javascript": (
                "const adj = new Map();\n"
                "const visited = new Set();"
            )
        },
        "walkthrough": "Starting at node A connected to B and C: BFS visits B and C at distance 1, then their unvisited neighbors at distance 2.",
        "when_to_use": "BFS for unweighted shortest paths; DFS for cycle detection, topological sorting, connected components.",
        "when_not_to_use": "Avoid adjacency matrices O(V^2) for sparse graphs where |E| << |V|^2.",
        "pitfalls": "Forgetting to mark nodes as visited immediately upon enqueueing in BFS, causing exponential duplicate visits and out-of-memory.",
        "practice_challenge": "Given an m x n 2D grid of '1's (land) and '0's (water), count the number of islands using BFS or DFS.",
        "notes": {
            "summary": "Networks of vertices and edges. Adjacency lists are standard. BFS finds shortest paths; DFS explores components.",
            "key_terms": [
                "**Vertex (Node)**: An entity or point in the graph.",
                "**Edge**: A connection linking two vertices.",
                "**Adjacency List**: Array/Map where each vertex lists its immediate outgoing neighbors.",
                "**Visited Set**: Hash set preventing infinite cycles."
            ],
            "formulas": "Time: O(V + E) for both BFS and DFS. Space: O(V) for visited set and queue/stack.",
            "cheat_sheet": [
                {"Algorithm": "BFS", "Data Structure": "Queue (FIFO)", "Primary Use": "Shortest Path (Unweighted)"},
                {"Algorithm": "DFS", "Data Structure": "Stack / Recursion", "Primary Use": "Backtracking / Cycle Detection"},
                {"Algorithm": "Dijkstra", "Data Structure": "Priority Queue", "Primary Use": "Weighted Shortest Path"}
            ]
        },
        "quiz": {
            "question": "What is the primary danger of running DFS or BFS without a 'visited' tracking mechanism?",
            "options": [
                "A) The time complexity becomes O(1).",
                "B) The algorithm enters an infinite loop if the graph contains any cycle.",
                "C) The compiler terminates the process immediately.",
                "D) Graph vertices automatically detach their edges."
            ],
            "correct_key": "B",
            "explanation": "If a cycle exists (e.g. A connects to B, B connects to A), traversing without a visited set cycles between A and B forever."
        }
    },

    "Dynamic Programming": {
        "display_name": "Dynamic Programming (DP)",
        "definition": "Dynamic Programming is an algorithmic optimization technique that solves complex problems by breaking them down into overlapping subproblems with optimal substructure, caching intermediate subproblem solutions to prevent redundant work.",
        "analogy": "Imagine writing '1 + 1 + 1 + 1 + 1' on a paper and asking what it equals (5). If you add another '+ 1' at the end, you don't recount from scratch—you simply remember the previous answer was 5 and add 1 to get 6!",
        "why_needed": "Transforms exponential O(2^N) brute-force recursive solutions into polynomial O(N) or O(N^2) time by guaranteeing each unique subproblem is solved exactly once.",
        "how_it_works": (
            "1. **Top-Down with Memoization**: Write the natural recursive relationship, storing results in a hash map or array cache.\n"
            "2. **Bottom-Up with Tabulation**: Solve base cases first, iteratively filling a DP table in topological subproblem order."
        ),
        "syntax": {
            "python": (
                "# Climbing Stairs: dp[i] = dp[i-1] + dp[i-2]\n"
                "def climb_stairs(n: int) -> int:\n"
                "    if n <= 2:\n"
                "        return n\n"
                "    dp = [0] * (n + 1)\n"
                "    dp[1], dp[2] = 1, 2\n"
                "    for i in range(3, n + 1):\n"
                "        dp[i] = dp[i - 1] + dp[i - 2]\n"
                "    return dp[n]"
            ),
            "c": (
                "int climbStairs(int n) {\n"
                "    if (n <= 2) return n;\n"
                "    int prev2 = 1, prev1 = 2, curr = 0;\n"
                "    for (int i = 3; i <= n; i++) {\n"
                "        curr = prev1 + prev2;\n"
                "        prev2 = prev1;\n"
                "        prev1 = curr;\n"
                "    }\n"
                "    return curr;\n"
                "}"
            ),
            "cpp": (
                "#include <vector>\n"
                "int climbStairs(int n) {\n"
                "    if (n <= 2) return n;\n"
                "    std::vector<int> dp(n + 1, 0);\n"
                "    dp[1] = 1; dp[2] = 2;\n"
                "    for (int i = 3; i <= n; i++) dp[i] = dp[i-1] + dp[i-2];\n"
                "    return dp[n];\n"
                "}"
            ),
            "java": (
                "public int climbStairs(int n) {\n"
                "    if (n <= 2) return n;\n"
                "    int[] dp = new int[n + 1];\n"
                "    dp[1] = 1; dp[2] = 2;\n"
                "    for (int i = 3; i <= n; i++) dp[i] = dp[i-1] + dp[i-2];\n"
                "    return dp[n];\n"
                "}"
            ),
            "javascript": (
                "function climbStairs(n) {\n"
                "    if (n <= 2) return n;\n"
                "    let prev2 = 1, prev1 = 2, curr = 0;\n"
                "    for (let i = 3; i <= n; i++) {\n"
                "        curr = prev1 + prev2;\n"
                "        prev2 = prev1;\n"
                "        prev1 = curr;\n"
                "    }\n"
                "    return curr;\n"
                "}"
            )
        },
        "walkthrough": "To climb 4 steps: base cases are step 1 (1 way) and step 2 (2 ways). Step 3 = 1 + 2 = 3 ways. Step 4 = 2 + 3 = 5 ways.",
        "when_to_use": "Optimization problems asking for min/max value, total ways, or possibility, where subproblems overlap.",
        "when_not_to_use": "When subproblems do not overlap (e.g. standard Mergesort where halves are completely disjoint).",
        "pitfalls": "Off-by-one errors in DP table sizing; calculating states before their prerequisite subproblems are ready.",
        "practice_challenge": "Given an array of coin denominations and an amount, find the fewest number of coins needed to make up that amount (Coin Change).",
        "notes": {
            "summary": "Caching subproblems avoids recomputation. Check for Optimal Substructure + Overlapping Subproblems.",
            "key_terms": [
                "**Overlapping Subproblems**: The same smaller problems are evaluated repeatedly.",
                "**Optimal Substructure**: The optimal solution to the problem contains optimal solutions to subproblems.",
                "**State Transition Equation**: The recurrence relation connecting dp[i] to earlier dp values."
            ],
            "formulas": "Time: (Number of States) * (Time per State Transition). Space: Size of DP table.",
            "cheat_sheet": [
                {"Approach": "Memoization", "Type": "Top-Down", "Pros": "Intuitive recursive structure"},
                {"Approach": "Tabulation", "Type": "Bottom-Up", "Pros": "No call stack overhead, space optimization"}
            ]
        },
        "quiz": {
            "question": "What two core properties must a problem have to be solved using Dynamic Programming?",
            "options": [
                "A) Monotonicity and Disjoint Partitions",
                "B) Overlapping Subproblems and Optimal Substructure",
                "C) Contiguous Memory and Logarithmic Depth",
                "D) Graph Adjacency and FIFO Ordering"
            ],
            "correct_key": "B",
            "explanation": "DP requires overlapping subproblems (so caching eliminates redundant calculations) and optimal substructure (optimal solution composed of optimal sub-solutions)."
        }
    },

    "Arrays": {
        "display_name": "Arrays & Subarrays",
        "definition": "An array is a contiguous block of memory holding a fixed number of elements of the same type, each accessible in O(1) time by index.",
        "analogy": "Think of a hotel floor: each room is numbered sequentially. You can walk directly to room 7 without checking rooms 1–6 first.",
        "why_needed": "Arrays are the simplest and most cache-friendly data structure. Most other structures (stacks, queues, heaps) are built on top of arrays.",
        "how_it_works": (
            "1. **Indexing**: `arr[i]` = base_address + i × element_size. O(1) access.\n"
            "2. **Traversal**: Iterate with a `for` loop from index 0 to N-1.\n"
            "3. **Insertion/Deletion**: Shifting elements costs O(N) in the worst case.\n"
            "4. **Subarray problems**: Sliding window / prefix sums reduce O(N²) brute force to O(N)."
        ),
        "syntax": {
            "python": (
                "# 1D Array\n"
                "arr = [10, 20, 30, 40, 50]\n"
                "print(arr[2])   # O(1) access → 30\n\n"
                "# Prefix Sum (subarray sum in O(1))\n"
                "prefix = [0] * (len(arr) + 1)\n"
                "for i, x in enumerate(arr):\n"
                "    prefix[i+1] = prefix[i] + x\n"
                "# Sum of arr[1..3] = prefix[4] - prefix[1] = 90 - 10 = 80\n"
            ),
            "c": (
                "#include <stdio.h>\n\n"
                "int main() {\n"
                "    int arr[] = {10, 20, 30, 40, 50};\n"
                "    int n = 5;\n"
                "    // Prefix sum\n"
                "    int prefix[6] = {0};\n"
                "    for (int i = 0; i < n; i++)\n"
                "        prefix[i+1] = prefix[i] + arr[i];\n"
                "    printf(\"Sum [1..3] = %d\\n\", prefix[4] - prefix[1]); // 80\n"
                "    return 0;\n"
                "}"
            ),
            "cpp": (
                "#include <vector>\n"
                "#include <iostream>\n"
                "using namespace std;\n\n"
                "int main() {\n"
                "    vector<int> arr = {10, 20, 30, 40, 50};\n"
                "    vector<int> prefix(arr.size() + 1, 0);\n"
                "    for (int i = 0; i < arr.size(); i++)\n"
                "        prefix[i+1] = prefix[i] + arr[i];\n"
                "    cout << prefix[4] - prefix[1] << endl; // 80\n"
                "}"
            ),
            "java": (
                "public class Arrays {\n"
                "    public static void main(String[] args) {\n"
                "        int[] arr = {10, 20, 30, 40, 50};\n"
                "        int[] prefix = new int[arr.length + 1];\n"
                "        for (int i = 0; i < arr.length; i++)\n"
                "            prefix[i+1] = prefix[i] + arr[i];\n"
                "        System.out.println(prefix[4] - prefix[1]); // 80\n"
                "    }\n"
                "}"
            ),
            "javascript": (
                "const arr = [10, 20, 30, 40, 50];\n"
                "const prefix = new Array(arr.length + 1).fill(0);\n"
                "for (let i = 0; i < arr.length; i++)\n"
                "    prefix[i+1] = prefix[i] + arr[i];\n"
                "console.log(prefix[4] - prefix[1]); // 80"
            )
        },
        "walkthrough": (
            "Finding maximum subarray sum (Kadane's Algorithm):\n"
            "```\n"
            "arr = [-2, 1, -3, 4, -1, 2, 1, -5, 4]\n"
            "max_sum = 4, current = 4\n"
            "→ 4-1=3, 3+2=5, 5+1=6 (max!) → answer: 6\n"
            "```\n"
            "Key insight: At each position, either extend current subarray or start fresh."
        ),
        "when_to_use": "Most problems involving indexed sequences, sliding window, prefix sums, two pointers, or matrix traversal.",
        "when_not_to_use": "When you need fast insertions/deletions in the middle (use Linked List), or when the size is unknown and grows dynamically (use ArrayList/vector).",
        "pitfalls": (
            "1. **Off-by-one errors**: Loop bounds `i < n` vs `i <= n`, array index 0-based.\n"
            "2. **Integer overflow**: Sum of array elements can exceed 32-bit int range.\n"
            "3. **In-place modification bugs**: Modifying while iterating without a copy."
        ),
        "practice_challenge": "Implement Kadane's Algorithm to find the contiguous subarray with the maximum sum. Input: `[-2, 1, -3, 4, -1, 2, 1, -5, 4]`. Expected: `6`.",
        "notes": {
            "summary": "Arrays provide O(1) random access by index. Prefix sums and sliding window convert O(N²) subarray problems to O(N).",
            "key_terms": [
                "**Prefix Sum**: prefix[i] = sum of arr[0..i-1]. Subarray sum in O(1).",
                "**Sliding Window**: Two pointers moving in the same direction to maintain a window.",
                "**Kadane's Algorithm**: O(N) maximum subarray sum.",
                "**Two Pointers**: Left and right pointers narrowing toward a target."
            ],
            "formulas": (
                "- Subarray sum [l..r] = prefix[r+1] - prefix[l]\n"
                "- Kadane's: curr = max(arr[i], curr + arr[i]); max_sum = max(max_sum, curr)"
            ),
            "cheat_sheet": [
                {"Pattern": "Subarray sum", "Technique": "Prefix Sum", "Time": "O(N) build, O(1) query"},
                {"Pattern": "Max subarray", "Technique": "Kadane's Algorithm", "Time": "O(N)"},
                {"Pattern": "Fixed-size window", "Technique": "Sliding Window", "Time": "O(N)"},
                {"Pattern": "Pair sum = target", "Technique": "Two Pointers (sorted)", "Time": "O(N)"}
            ]
        },
        "quiz": {
            "question": "What is the time complexity of finding the sum of a subarray arr[l..r] using prefix sums?",
            "options": [
                "A) O(N) — scan elements from l to r",
                "B) O(1) — direct lookup in prefix array",
                "C) O(log N) — binary search on prefix array",
                "D) O(N²) — nested loop required"
            ],
            "correct_key": "B",
            "explanation": "prefix[r+1] - prefix[l] gives the sum in O(1) after O(N) preprocessing."
        }
    },

    "Strings": {
        "display_name": "Strings & Pattern Matching",
        "definition": "A string is an immutable (in most languages) sequence of characters. String problems involve searching, manipulating, or matching character sequences.",
        "analogy": "A string is like a sentence in a book: you can read any word by position, but rewriting requires creating a new book.",
        "why_needed": "String manipulation underpins text processing, compilers, data serialization, network protocols, DNA sequencing, and more.",
        "how_it_works": (
            "1. **Indexing**: `s[i]` gives the character at position i in O(1).\n"
            "2. **Substring**: `s[l:r]` extracts characters from l to r-1.\n"
            "3. **Common patterns**: Sliding window for substring problems; two-pointer for palindrome checks; HashMap for anagram detection."
        ),
        "syntax": {
            "python": (
                "s = 'hello world'\n\n"
                "# Reverse a string\n"
                "rev = s[::-1]  # 'dlrow olleh'\n\n"
                "# Check palindrome\n"
                "def is_palindrome(s):\n"
                "    return s == s[::-1]\n\n"
                "# Count character frequency\n"
                "from collections import Counter\n"
                "freq = Counter(s)  # {'l': 3, 'o': 2, ...}\n\n"
                "# Sliding window: longest substring without repeat\n"
                "def lengthOfLongestSubstring(s):\n"
                "    seen = {}\n"
                "    left = max_len = 0\n"
                "    for right, c in enumerate(s):\n"
                "        if c in seen and seen[c] >= left:\n"
                "            left = seen[c] + 1\n"
                "        seen[c] = right\n"
                "        max_len = max(max_len, right - left + 1)\n"
                "    return max_len"
            ),
            "c": (
                '#include <stdio.h>\n'
                '#include <string.h>\n\n'
                'int isPalindrome(const char *s, int n) {\n'
                '    int l = 0, r = n - 1;\n'
                '    while (l < r) {\n'
                '        if (s[l] != s[r]) return 0;\n'
                '        l++; r--;\n'
                '    }\n'
                '    return 1;\n'
                '}\n\n'
                'int main() {\n'
                '    const char *s = "racecar";\n'
                '    printf("%d\\n", isPalindrome(s, strlen(s))); // 1 (true)\n'
                '    return 0;\n'
                '}'
            ),
            "cpp": (
                '#include <string>\n'
                '#include <algorithm>\n'
                '#include <iostream>\n'
                'using namespace std;\n\n'
                'bool isPalindrome(string s) {\n'
                '    string rev = s;\n'
                '    reverse(rev.begin(), rev.end());\n'
                '    return s == rev;\n'
                '}\n'
                'int main() {\n'
                '    cout << isPalindrome("racecar") << endl; // 1\n'
                '}'
            ),
            "java": (
                'public class StringDemo {\n'
                '    public static boolean isPalindrome(String s) {\n'
                '        return s.equals(new StringBuilder(s).reverse().toString());\n'
                '    }\n'
                '    public static void main(String[] args) {\n'
                '        System.out.println(isPalindrome("racecar")); // true\n'
                '    }\n'
                '}'
            ),
            "javascript": (
                'function isPalindrome(s) {\n'
                '    return s === s.split("").reverse().join("");\n'
                '}\n'
                'console.log(isPalindrome("racecar")); // true'
            )
        },
        "walkthrough": (
            "Checking anagram of 'listen' and 'silent':\n"
            "- Sort both: 'eilnst' == 'eilnst' → YES, anagram!\n\n"
            "OR use character frequency map:\n"
            "```python\n"
            "Counter('listen') == Counter('silent')  # True\n"
            "```"
        ),
        "when_to_use": "Text search, pattern matching, palindrome/anagram detection, parsing, tokenization.",
        "when_not_to_use": "When mutable buffer behavior is needed (use char[] in C or StringBuilder in Java).",
        "pitfalls": (
            "1. **String immutability**: Concatenating strings in a loop builds O(N²) copies; use StringBuilder or join().\n"
            "2. **Off-by-one in substrings**: Python s[l:r] excludes r; Java substring(l, r) also excludes r.\n"
            "3. **Unicode vs ASCII**: `len()` in Python counts code points, not bytes."
        ),
        "practice_challenge": "Implement a function that checks whether two strings are anagrams. Input: 'listen', 'silent'. Expected: True.",
        "notes": {
            "summary": "String problems often reduce to frequency counting (HashMap), two pointers, or sliding window. Know your language's string immutability rules.",
            "key_terms": [
                "**Palindrome**: String that reads the same forwards and backwards.",
                "**Anagram**: Two strings with identical character frequencies.",
                "**Sliding Window**: Efficient O(N) substring search technique.",
                "**KMP Algorithm**: O(N+M) pattern matching using failure function."
            ],
            "formulas": (
                "- Anagram check: sort both O(N log N) or frequency map O(N)\n"
                "- Sliding window time: O(N) with O(alphabet) space"
            ),
            "cheat_sheet": [
                {"Problem Type": "Palindrome", "Best Approach": "Two pointers or reverse"},
                {"Problem Type": "Anagram", "Best Approach": "Character frequency HashMap"},
                {"Problem Type": "Longest unique substring", "Best Approach": "Sliding window"},
                {"Problem Type": "Pattern search", "Best Approach": "KMP / Rabin-Karp"}
            ]
        },
        "quiz": {
            "question": "What is the most efficient way to check if two strings are anagrams?",
            "options": [
                "A) Compare all character pairs with nested loops — O(N²)",
                "B) Sort both strings and compare — O(N log N)",
                "C) Build a character frequency map for each and compare — O(N)",
                "D) Check if one string is a substring of the other"
            ],
            "correct_key": "C",
            "explanation": "A frequency HashMap/Counter runs in O(N) and uses O(26) = O(1) extra space for lowercase English letters."
        }
    },

    "Hash Table": {
        "display_name": "Hash Tables & HashMaps",
        "definition": "A Hash Table maps keys to values using a hash function that converts a key into a bucket index, providing O(1) average-time insertions, lookups, and deletions.",
        "analogy": "A dictionary (book): you look up a word (key) directly by its alphabetical position rather than reading every page. The hash function is the alphabetical index.",
        "why_needed": "Hash tables power O(1) frequency counting, fast lookups, caching (LRU), and set membership checks that would otherwise require O(N) linear scans.",
        "how_it_works": (
            "1. **Hash Function**: Converts key to integer → bucket index = hash(key) % table_size.\n"
            "2. **Bucket**: Each bucket stores one or more key-value pairs.\n"
            "3. **Collision Handling**: When two keys hash to the same bucket:\n"
            "   - **Chaining**: Store a linked list in the bucket.\n"
            "   - **Open Addressing**: Probe adjacent buckets.\n"
            "4. **Load Factor**: ratio = entries / buckets. High load → more collisions. Rehash when load > 0.75."
        ),
        "syntax": {
            "python": (
                "# Python dict = built-in hash table\n"
                "freq = {}  # or defaultdict(int)\n\n"
                "words = ['apple', 'banana', 'apple', 'cherry', 'banana', 'apple']\n"
                "for word in words:\n"
                "    freq[word] = freq.get(word, 0) + 1\n\n"
                "print(freq)  # {'apple': 3, 'banana': 2, 'cherry': 1}\n\n"
                "# Two Sum problem with hash map\n"
                "def two_sum(nums, target):\n"
                "    seen = {}  # value → index\n"
                "    for i, num in enumerate(nums):\n"
                "        complement = target - num\n"
                "        if complement in seen:\n"
                "            return [seen[complement], i]\n"
                "        seen[num] = i\n"
                "    return []"
            ),
            "c": (
                "// C doesn't have a built-in hash map; use frequency arrays for simple cases\n"
                "#include <stdio.h>\n"
                "#include <string.h>\n\n"
                "int main() {\n"
                "    int freq[256] = {0}; // ASCII frequency map\n"
                "    const char *s = \"hello\";\n"
                "    for (int i = 0; s[i]; i++) freq[(unsigned char)s[i]]++;\n"
                "    printf(\"'l' appears %d times\\n\", freq['l']); // 2\n"
                "    return 0;\n"
                "}"
            ),
            "cpp": (
                "#include <unordered_map>\n"
                "#include <iostream>\n"
                "using namespace std;\n\n"
                "int main() {\n"
                "    unordered_map<string, int> freq;\n"
                "    vector<string> words = {\"apple\", \"banana\", \"apple\"};\n"
                "    for (const auto& w : words) freq[w]++;\n"
                "    cout << freq[\"apple\"] << endl; // 2\n"
                "    return 0;\n"
                "}"
            ),
            "java": (
                "import java.util.HashMap;\n\n"
                "public class HashDemo {\n"
                "    public static void main(String[] args) {\n"
                "        HashMap<String, Integer> freq = new HashMap<>();\n"
                "        String[] words = {\"apple\", \"banana\", \"apple\"};\n"
                "        for (String w : words)\n"
                "            freq.put(w, freq.getOrDefault(w, 0) + 1);\n"
                "        System.out.println(freq.get(\"apple\")); // 2\n"
                "    }\n"
                "}"
            ),
            "javascript": (
                "const freq = {};\n"
                "const words = ['apple', 'banana', 'apple'];\n"
                "for (const w of words) freq[w] = (freq[w] || 0) + 1;\n"
                "console.log(freq['apple']); // 2"
            )
        },
        "walkthrough": (
            "Two Sum solution trace:\n"
            "```\n"
            "nums = [2, 7, 11, 15], target = 9\n"
            "i=0: num=2, complement=7, not in seen → seen={2:0}\n"
            "i=1: num=7, complement=2, 2 IS in seen! → return [0, 1]\n"
            "```\n"
            "O(N) using hash map vs O(N²) brute force!"
        ),
        "when_to_use": "Frequency counting, Two Sum / K-Sum problems, grouping anagrams, caching results, fast membership testing.",
        "when_not_to_use": "When key ordering matters (use TreeMap/SortedDict), or when memory is extremely constrained.",
        "pitfalls": (
            "1. **Hash collisions**: Rare but degrade O(1) to O(N) in worst case with adversarial keys.\n"
            "2. **Mutable keys in Python**: Lists/dicts cannot be dict keys (not hashable).\n"
            "3. **Iteration order**: Python dicts (3.7+) preserve insertion order, but Java HashMap does not."
        ),
        "practice_challenge": "Solve Two Sum: Given `nums = [2, 7, 11, 15]` and `target = 9`, return indices of the two numbers that add to target. Use O(N) solution with a hash map.",
        "notes": {
            "summary": "Hash Tables provide O(1) average-case insert/lookup/delete. They're the secret weapon for reducing O(N²) brute force to O(N).",
            "key_terms": [
                "**Hash Function**: Converts key → integer bucket index.",
                "**Collision**: Two keys mapping to the same bucket.",
                "**Load Factor**: entries/capacity ratio; rehash when > 0.75.",
                "**Open Addressing**: Probing strategy for collision resolution."
            ],
            "formulas": (
                "- Average time: O(1) insert/lookup/delete\n"
                "- Worst case (all collide): O(N)\n"
                "- Space: O(N) for N key-value pairs"
            ),
            "cheat_sheet": [
                {"Operation": "Insert / Update", "Avg Time": "O(1)"},
                {"Operation": "Lookup by Key", "Avg Time": "O(1)"},
                {"Operation": "Delete by Key", "Avg Time": "O(1)"},
                {"Operation": "Iterate all", "Avg Time": "O(N)"}
            ]
        },
        "quiz": {
            "question": "Why is the average-case lookup in a hash table O(1) rather than O(N)?",
            "options": [
                "A) The hash function sorts keys so binary search is possible.",
                "B) The hash function maps keys to direct bucket indices, avoiding linear scan.",
                "C) Hash tables store keys in contiguous sorted memory.",
                "D) Hash tables use tree balancing to ensure O(log N) lookups."
            ],
            "correct_key": "B",
            "explanation": "The hash function maps a key directly to a bucket index in O(1) arithmetic, bypassing the need to scan all entries."
        }
    },

    "Two Pointers": {
        "display_name": "Two Pointers & Sliding Window",
        "definition": "Two Pointers is a technique that uses two index variables moving through an array to reduce O(N²) brute-force solutions to O(N).",
        "analogy": "Like two readers scanning a book from opposite ends, meeting in the middle — far more efficient than all possible page-pair combinations.",
        "why_needed": "Many array and string problems that naively require nested loops (O(N²)) can be solved in O(N) by maintaining a left and right pointer intelligently.",
        "how_it_works": (
            "**Pattern 1 — Opposite Ends** (sorted array pair sum):\n"
            "- Start left=0, right=N-1.\n"
            "- If sum == target: found! If sum < target: move left right. If sum > target: move right left.\n\n"
            "**Pattern 2 — Same Direction** (sliding window):\n"
            "- Both pointers move left-to-right.\n"
            "- right expands window; left shrinks when constraint violated.\n"
            "- Track window state (sum, character frequency, etc.)."
        ),
        "syntax": {
            "python": (
                "# Pattern 1: Two sum in sorted array\n"
                "def two_sum_sorted(nums, target):\n"
                "    left, right = 0, len(nums) - 1\n"
                "    while left < right:\n"
                "        s = nums[left] + nums[right]\n"
                "        if s == target:\n"
                "            return [left, right]\n"
                "        elif s < target:\n"
                "            left += 1\n"
                "        else:\n"
                "            right -= 1\n"
                "    return []\n\n"
                "# Pattern 2: Longest substring without repeating characters\n"
                "def lengthOfLongestSubstring(s):\n"
                "    seen = {}\n"
                "    left = max_len = 0\n"
                "    for right, c in enumerate(s):\n"
                "        if c in seen and seen[c] >= left:\n"
                "            left = seen[c] + 1\n"
                "        seen[c] = right\n"
                "        max_len = max(max_len, right - left + 1)\n"
                "    return max_len"
            ),
            "c": (
                "#include <stdio.h>\n\n"
                "// Check if array has a pair summing to target (sorted input)\n"
                "int hasPairSum(int arr[], int n, int target) {\n"
                "    int left = 0, right = n - 1;\n"
                "    while (left < right) {\n"
                "        int sum = arr[left] + arr[right];\n"
                "        if (sum == target) return 1;\n"
                "        else if (sum < target) left++;\n"
                "        else right--;\n"
                "    }\n"
                "    return 0;\n"
                "}"
            ),
            "cpp": (
                "#include <vector>\n"
                "using namespace std;\n\n"
                "vector<int> twoSum(vector<int>& nums, int target) {\n"
                "    int left = 0, right = nums.size() - 1;\n"
                "    while (left < right) {\n"
                "        int sum = nums[left] + nums[right];\n"
                "        if (sum == target) return {left, right};\n"
                "        else if (sum < target) left++;\n"
                "        else right--;\n"
                "    }\n"
                "    return {};\n"
                "}"
            ),
            "java": (
                "public class TwoPointers {\n"
                "    public int[] twoSum(int[] nums, int target) {\n"
                "        int left = 0, right = nums.length - 1;\n"
                "        while (left < right) {\n"
                "            int sum = nums[left] + nums[right];\n"
                "            if (sum == target) return new int[]{left, right};\n"
                "            else if (sum < target) left++;\n"
                "            else right--;\n"
                "        }\n"
                "        return new int[]{};\n"
                "    }\n"
                "}"
            ),
            "javascript": (
                "function twoSum(nums, target) {\n"
                "    let left = 0, right = nums.length - 1;\n"
                "    while (left < right) {\n"
                "        const sum = nums[left] + nums[right];\n"
                "        if (sum === target) return [left, right];\n"
                "        else if (sum < target) left++;\n"
                "        else right--;\n"
                "    }\n"
                "    return [];\n"
                "}"
            )
        },
        "walkthrough": (
            "Two Sum on sorted array `[1, 3, 6, 10, 11]`, target=9:\n"
            "- left=0 (1), right=4 (11): sum=12 > 9 → right--\n"
            "- left=0 (1), right=3 (10): sum=11 > 9 → right--\n"
            "- left=0 (1), right=2 (6): sum=7 < 9 → left++\n"
            "- left=1 (3), right=2 (6): sum=9 == 9 → Found! [1, 2]"
        ),
        "when_to_use": "Sorted array pair/triplet problems, palindrome checks, sliding window (substring, subarray), remove duplicates in-place.",
        "when_not_to_use": "Unsorted arrays where ordering is required for the pointer logic (sort first, or use hash map instead).",
        "pitfalls": (
            "1. **Not sorting first**: Two-pointer opposite-ends only works on sorted arrays.\n"
            "2. **Duplicate handling**: For 3Sum, skip duplicate left/right values after finding a match.\n"
            "3. **Window state**: In sliding window, always update state (sum/freq) before moving pointers."
        ),
        "practice_challenge": "Given sorted array `[1, 3, 6, 10, 11]` and target `9`, return the pair of indices that sum to the target using two pointers in O(N).",
        "notes": {
            "summary": "Two Pointers reduces O(N²) to O(N) on sorted arrays. Sliding window uses same-direction two pointers for substring/subarray problems.",
            "key_terms": [
                "**Left Pointer**: Lower boundary of current window or range.",
                "**Right Pointer**: Upper boundary, expands the search space.",
                "**Window**: The active range [left, right] being considered.",
                "**Constraint**: Condition that must hold for the window to be valid."
            ],
            "formulas": (
                "- Time: O(N) — each pointer moves at most N steps total\n"
                "- Space: O(1) for the pointers themselves"
            ),
            "cheat_sheet": [
                {"Pattern": "Sorted pair sum", "Direction": "Opposite ends", "Complexity": "O(N)"},
                {"Pattern": "Longest valid window", "Direction": "Same direction", "Complexity": "O(N)"},
                {"Pattern": "Palindrome check", "Direction": "Opposite ends", "Complexity": "O(N)"},
                {"Pattern": "Remove duplicates", "Direction": "Same direction (slow/fast)", "Complexity": "O(N)"}
            ]
        },
        "quiz": {
            "question": "When using two pointers on a sorted array to find a pair summing to a target, what do you do if the current sum is LESS than the target?",
            "options": [
                "A) Decrement the right pointer to reduce the sum.",
                "B) Increment the left pointer to increase the sum.",
                "C) Restart from the beginning of the array.",
                "D) Use binary search to find the complement."
            ],
            "correct_key": "B",
            "explanation": "On a sorted array, incrementing left increases the smaller value, thus increasing the sum toward the target."
        }
    },

    "OOP": {
        "display_name": "Object-Oriented Programming (OOP)",
        "definition": "OOP is a programming paradigm that organizes code into objects — bundles of data (attributes) and behavior (methods) — modeled after real-world entities.",
        "analogy": "A class is a blueprint for a house. An object is the actual house built from that blueprint. Many houses (objects) can be built from the same blueprint (class).",
        "why_needed": "OOP enables code reuse (inheritance), modular design (encapsulation), and flexible interfaces (polymorphism) — making large software systems maintainable.",
        "how_it_works": (
            "**4 Pillars of OOP:**\n"
            "1. **Encapsulation**: Bundle data & methods; hide internal state with `private`/`protected`.\n"
            "2. **Inheritance**: Child class inherits attributes and methods of parent class (`extends`/`:`).\n"
            "3. **Polymorphism**: Different classes respond to the same method call differently (method overriding).\n"
            "4. **Abstraction**: Expose only necessary interfaces; hide implementation details."
        ),
        "syntax": {
            "python": (
                "class Animal:\n"
                "    def __init__(self, name):\n"
                "        self.name = name  # encapsulation\n\n"
                "    def speak(self):\n"
                "        return 'Some sound'  # base method\n\n"
                "class Dog(Animal):  # inheritance\n"
                "    def speak(self):  # polymorphism: override\n"
                "        return f'{self.name} says Woof!'\n\n"
                "class Cat(Animal):\n"
                "    def speak(self):\n"
                "        return f'{self.name} says Meow!'\n\n"
                "animals = [Dog('Rex'), Cat('Luna')]\n"
                "for a in animals:\n"
                "    print(a.speak())  # Polymorphic dispatch"
            ),
            "java": (
                "public abstract class Animal {\n"
                "    protected String name;\n"
                "    public Animal(String name) { this.name = name; }\n"
                "    public abstract String speak(); // abstraction\n"
                "}\n\n"
                "public class Dog extends Animal {\n"
                "    public Dog(String name) { super(name); }\n"
                "    @Override\n"
                "    public String speak() { return name + \" says Woof!\"; }\n"
                "}"
            ),
            "cpp": (
                "#include <iostream>\n"
                "#include <string>\n"
                "using namespace std;\n\n"
                "class Animal {\n"
                "public:\n"
                "    string name;\n"
                "    Animal(string n) : name(n) {}\n"
                "    virtual string speak() { return \"Some sound\"; } // polymorphism\n"
                "};\n\n"
                "class Dog : public Animal {\n"
                "public:\n"
                "    Dog(string n) : Animal(n) {}\n"
                "    string speak() override { return name + \" says Woof!\"; }\n"
                "};"
            ),
            "javascript": (
                "class Animal {\n"
                "    constructor(name) { this.name = name; }\n"
                "    speak() { return 'Some sound'; }\n"
                "}\n\n"
                "class Dog extends Animal {\n"
                "    speak() { return `${this.name} says Woof!`; }\n"
                "}\n\n"
                "const animals = [new Dog('Rex')];\n"
                "animals.forEach(a => console.log(a.speak()));"
            ),
            "c": (
                "/* C doesn't have native OOP — simulate with structs + function pointers */\n"
                "#include <stdio.h>\n\n"
                "typedef struct {\n"
                "    char name[50];\n"
                "    void (*speak)(const char*);\n"
                "} Animal;\n\n"
                "void dogSpeak(const char* name) { printf(\"%s says Woof!\\n\", name); }\n\n"
                "int main() {\n"
                "    Animal rex = {\"Rex\", dogSpeak};\n"
                "    rex.speak(rex.name);\n"
                "    return 0;\n"
                "}"
            )
        },
        "walkthrough": (
            "When `dog.speak()` is called:\n"
            "1. Python looks up `speak` in `Dog` class first → finds override → calls `Dog.speak()`.\n"
            "2. If not found in `Dog`, it climbs the MRO (Method Resolution Order) to `Animal`.\n"
            "3. This is **dynamic dispatch** — the type at runtime determines which method runs."
        ),
        "when_to_use": "Large codebases, modeling real-world entities, game development, GUI frameworks, and any system where components have clear roles and relationships.",
        "when_not_to_use": "Simple scripts, data transformation pipelines, or purely functional problems where OOP adds unnecessary complexity.",
        "pitfalls": (
            "1. **Over-engineering**: Creating deep inheritance hierarchies that are hard to maintain.\n"
            "2. **Forgetting `self`/`this`**: Methods must reference the instance explicitly.\n"
            "3. **Mutable default arguments in Python**: `def __init__(self, items=[])` shares the list across instances!"
        ),
        "practice_challenge": "Create a `Shape` base class with an `area()` method. Create `Circle` and `Rectangle` subclasses that override `area()`. Demonstrate polymorphism by calling `area()` on a list of shapes.",
        "notes": {
            "summary": "OOP organizes code into objects with Encapsulation (data hiding), Inheritance (code reuse), Polymorphism (method override), and Abstraction (interface design).",
            "key_terms": [
                "**Class**: Blueprint/template defining attributes and methods.",
                "**Object**: An instance of a class with specific state.",
                "**Inheritance**: Child class extends parent — reuses code.",
                "**Polymorphism**: Same method name, different behavior per subclass.",
                "**Encapsulation**: Private data + public interface.",
                "**Abstraction**: Abstract classes/interfaces hide implementation."
            ],
            "formulas": (
                "- Method Resolution Order (MRO): C3 linearization in Python.\n"
                "- `isinstance(obj, ClassName)` checks runtime type."
            ),
            "cheat_sheet": [
                {"Concept": "Encapsulation", "Keyword": "private/protected/self"},
                {"Concept": "Inheritance", "Keyword": "extends / class B(A)"},
                {"Concept": "Polymorphism", "Keyword": "@Override / def speak()"},
                {"Concept": "Abstraction", "Keyword": "abstract class / ABC"}
            ]
        },
        "quiz": {
            "question": "Which OOP pillar allows a subclass to provide a different implementation of a method defined in its parent class?",
            "options": [
                "A) Encapsulation",
                "B) Abstraction",
                "C) Polymorphism (Method Overriding)",
                "D) Inheritance (Method Overloading)"
            ],
            "correct_key": "C",
            "explanation": "Polymorphism via method overriding allows the child class to redefine the parent's method, enabling different behavior for the same method call."
        }
    }
}

COMPARISON_GUIDES: Dict[str, Dict[str, Any]] = {
    "stack_vs_queue": {
        "title": "Stack vs. Queue: Comprehensive Comparison",
        "summary": "Both Stack and Queue are fundamental linear data structures, but they process elements in opposite orders.",
        "markdown_table": (
            "| Feature | Stack | Queue |\n"
            "| :--- | :--- | :--- |\n"
            "| **Access Order** | **LIFO** (Last-In, First-Out) | **FIFO** (First-In, First-Out) |\n"
            "| **Insertion Point** | Top (`push`) | Rear / Tail (`enqueue`) |\n"
            "| **Removal Point** | Top (`pop`) | Front / Head (`dequeue`) |\n"
            "| **Mental Model** | Spring-loaded plate dispenser | Line of customers at cashier |\n"
            "| **Core Traversal** | Depth-First Search (DFS) | Breadth-First Search (BFS) |\n"
            "| **Canonical Uses** | Undo/Redo, Syntax Parsing, Call Stack | Job scheduling, Printer spooler, Buffers |\n"
            "| **Time Complexity** | Push O(1), Pop O(1), Peek O(1) | Enqueue O(1), Dequeue O(1), Front O(1) |\n"
            "| **Space Complexity** | O(N) auxiliary | O(N) auxiliary |"
        ),
        "code_snippet": (
            "# Quick Python demonstration:\n"
            "# 1. STACK (LIFO)\n"
            "stack = []\n"
            "stack.append('A'); stack.append('B'); stack.append('C')\n"
            "print('Stack Pop:', stack.pop())  # 'C' (last pushed is first out)\n\n"
            "# 2. QUEUE (FIFO)\n"
            "from collections import deque\n"
            "queue = deque()\n"
            "queue.append('A'); queue.append('B'); queue.append('C')\n"
            "print('Queue Popleft:', queue.popleft())  # 'A' (first enqueued is first out)"
        )
    },
    "bfs_vs_dfs": {
        "title": "BFS vs. DFS: Graph & Tree Traversal Comparison",
        "summary": "BFS and DFS are complementary search algorithms exploring network structures.",
        "markdown_table": (
            "| Feature | BFS (Breadth-First Search) | DFS (Depth-First Search) |\n"
            "| :--- | :--- | :--- |\n"
            "| **Exploration Style** | Level-by-level (concentric circles) | Path-by-path (dives deep to leaf) |\n"
            "| **Underlying Structure** | Queue (FIFO) | Stack / Recursion (LIFO) |\n"
            "| **Shortest Path?** | Yes (guaranteed on unweighted graphs) | No (may find longer paths first) |\n"
            "| **Memory Consumption** | O(Width of tree/graph) | O(Depth / Height of tree) |\n"
            "| **Best For** | Shortest path, level-order traversal | Maze solving, cycle detection, topological sort |"
        ),
        "code_snippet": (
            "# BFS uses deque (FIFO), DFS uses list/stack or recursion (LIFO)"
        )
    },
    "array_vs_linked_list": {
        "title": "Array vs. Linked List: Core Trade-offs",
        "summary": "Contiguous memory vs. dynamic pointer-linked nodes.",
        "markdown_table": (
            "| Dimension | Dynamic Array (Vector) | Singly Linked List |\n"
            "| :--- | :--- | :--- |\n"
            "| **Random Index Access** | O(1) instant (`arr[i]`) | O(N) sequential traversal |\n"
            "| **Insert/Delete at Head**| O(N) (shifts all elements) | O(1) constant pointer rewiring |\n"
            "| **Insert/Delete at Tail**| O(1) amortized | O(1) if tail pointer tracked, else O(N) |\n"
            "| **Memory Layout** | Contiguous (great CPU cache locality) | Disjoint nodes (pointer overhead) |\n"
            "| **Resizing Cost** | O(N) copy on array reallocation | O(1) incremental per node |"
        ),
        "code_snippet": ""
    }
}
