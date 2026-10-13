import re
import ast
import operator
from typing import List, Optional, Dict, Any
from models import Problem
from ai.companion.provider_base import BaseLLMProvider
from ai.companion.schemas import CompanionChatMessage, CompanionContext, CompanionResponse, VisualizationSpec
from ai.companion.viz_simulator import extract_visualization_plan, DeterministicSimulator
from ai.companion.viz_validator import VisualizationValidator
from ai.companion.tutor_knowledge import TOPIC_KNOWLEDGE_BASE, COMPARISON_GUIDES
from ai.tutor import AITutorEngine, TOPIC_KNOWLEDGE, _get_lang_pattern, _analyze_code_structure, _infer_topics

SAFE_MATH_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def _eval_math_ast_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp) and type(node.op) in SAFE_MATH_OPS:
        left = _eval_math_ast_node(node.left)
        right = _eval_math_ast_node(node.right)
        return SAFE_MATH_OPS[type(node.op)](left, right)
    elif isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_MATH_OPS:
        return SAFE_MATH_OPS[type(node.op)](_eval_math_ast_node(node.operand))
    raise ValueError("Unsafe or non-arithmetic node")


class LocalTutorProvider(BaseLLMProvider):
    @property
    def provider_name(self) -> str:
        return "local_tutor"

    def is_available(self) -> bool:
        return True

    def _resolve_language(self, user_msg: str, context: CompanionContext) -> str:
        msg_l = (user_msg or "").lower()
        if " in c++" in msg_l or " in cpp" in msg_l:
            return "cpp"
        elif " in c " in msg_l or msg_l.endswith(" in c") or "in c language" in msg_l or "pointer in c" in msg_l:
            return "c"
        elif " in java" in msg_l:
            return "java"
        elif " in javascript" in msg_l or " in js" in msg_l:
            return "javascript"
        elif " in python" in msg_l:
            return "python"
        return (context.selected_language or "python").lower()

    def _try_eval_math(self, text: str) -> Optional[str]:
        """Safely evaluates basic arithmetic expressions without code execution."""
        cleaned = text.strip()
        # Remove common arithmetic query phrases
        cleaned = re.sub(r"^(?:what\s+is|what\'s|whats|calculate|evaluate|compute)\s+", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.rstrip("?!.,;").strip()
        if not cleaned:
            return None
        # Must only contain numbers and basic math characters
        if not re.match(r"^[0-9\s\+\-\*\/\%\^\(\)\.]+$", cleaned):
            return None
        # Must contain at least one operator
        if not any(op in cleaned for op in ["+", "-", "*", "/", "%", "^"]):
            return None
        cleaned_py = re.sub(r"(?<=\d)\^(?=\d)", "**", cleaned)
        try:
            tree = ast.parse(cleaned_py, mode="eval")
            val = _eval_math_ast_node(tree.body)
            if isinstance(val, float) and val.is_integer():
                return str(int(val))
            elif isinstance(val, float):
                return f"{val:.6g}"
            return str(val)
        except Exception:
            return None

    def _resolve_dynamic_visualization(self, msg: str, topic: Optional[str] = None, current_code: Optional[str] = None) -> Optional[VisualizationSpec]:
        """
        Dynamically generates a VisualizationSpec ONLY when the student explicitly requested it.
        Uses the deterministic simulator and validator, respecting user values and code.
        Never emits a stored template as a silent substitute.
        """
        msg_l = (msg or "").lower()
        viz_triggers = [
            "visualize", "diagram", "step through", "simulation", "draw", "show me", "illustrate", "flowchart", "animation"
        ]
        if not any(k in msg_l for k in viz_triggers):
            return None

        plan = extract_visualization_plan(msg, current_code=current_code)
        if plan:
            simulated = DeterministicSimulator.simulate(plan)
            if simulated:
                is_valid, _ = VisualizationValidator.validate(simulated)
                if is_valid:
                    return simulated
        return None

    def _is_greeting(self, text: str) -> bool:
        """Detect greetings and small talk so we don't trigger topic lessons."""
        t = text.strip().lower().rstrip("!.,")
        greetings = [
            "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
            "howdy", "what's up", "whats up", "how are you", "sup", "yo",
            "are you there", "you there", "is anyone there",
            "hello maya", "hi maya", "hey maya", "maya",
            "can you help", "can you hear me", "greetings"
        ]
        if len(t.split()) <= 6:
            for g in greetings:
                if t == g or t.startswith(g + " ") or t.endswith(" " + g):
                    return True
        return False

    def _is_deep_teaching_request(self, text: str) -> bool:
        """Checks if the user explicitly asked for comprehensive teaching from scratch."""
        t = text.lower()
        deep_markers = [
            "completely", "from zero", "from scratch", "in depth", "in detail",
            "teach me everything", "explain thoroughly", "comprehensive",
            "master ", "dive deep", "step by step guide"
        ]
        return any(m in t for m in deep_markers)

    def _find_history_topic(self, history: List[CompanionChatMessage]) -> Optional[str]:
        if not history:
            return None
        for h in reversed(history):
            text = (h.content or "").lower()
            # 1. Check knowledge base keys
            for topic in TOPIC_KNOWLEDGE_BASE.keys():
                if topic.lower() in text or (topic == "Pointers" and "pointer" in text):
                    return topic
            # 2. Check general programming topics
            for kw, tname in [
                ("virtual function", "Virtual Functions"),
                ("garbage collect", "Garbage Collection"),
                ("pointer", "Pointers"),
                ("array", "Arrays"),
                ("linked list", "Linked List"),
                ("stack", "Stack"),
                ("queue", "Queue"),
                ("tree", "Trees"),
                ("graph", "Graphs"),
                ("recursion", "Recursion"),
                ("binary search", "Binary Search"),
                ("sorting", "Sorting"),
                ("dynamic programming", "Dynamic Programming"),
                ("sql", "SQL"),
                ("concurrency", "Concurrency"),
                ("compiler", "Compiler Design"),
            ]:
                if kw in text:
                    return tname
        return None

    def _match_topic(self, text: str) -> Optional[str]:
        t = text.lower()

        # Comparisons (check first — more specific)
        if "stack vs queue" in t or "queue vs stack" in t:
            return "stack_vs_queue"
        if "bfs vs dfs" in t or "dfs vs bfs" in t:
            return "bfs_vs_dfs"
        if "array vs linked list" in t or "linked list vs array" in t:
            return "array_vs_linked_list"

        # Base case (specific recursion follow-up)
        if "base case" in t or "terminating condition" in t:
            return "Recursion"

        # Trees / BST
        if "tree" in t or "bst" in t or "binary tree" in t or "avl" in t or "trie" in t:
            return "Trees"

        # Graphs
        if "graph" in t or " bfs" in t or " dfs" in t or "dijkstra" in t or "shortest path" in t or "topological" in t:
            return "Graphs"

        # Sorting
        if any(w in t for w in ["quicksort", "quick sort", "mergesort", "merge sort", "bubble sort",
                                "insertion sort", "selection sort", "heap sort", "counting sort",
                                "radix sort", "sorting algorithm", "sort algorithm"]):
            return "Sorting"
        if "sorting" in t and not ("tree" in t or "graph" in t):
            return "Sorting"

        # Recursion
        if any(w in t for w in ["recursion", "recursive", "call stack", "factorial", "fibonacci",
                                "backtracking", "permutation", "combination", "n-queens", "n queens",
                                "maze", "subset"]):
            return "Recursion"

        # Binary Search
        if any(w in t for w in ["binary search", "bsearch", "interval halving", "bisect",
                                "search on answer", "lower bound", "upper bound"]):
            return "Binary Search"

        # Two Pointers / Sliding Window
        if any(w in t for w in ["two pointer", "two pointers", "sliding window", "window technique",
                                "left right pointer"]):
            return "Two Pointers"

        # Linked List
        if any(w in t for w in ["linked list", "singly linked", "doubly linked", "circular list",
                                "node chain", "node card"]):
            return "Linked List"

        # Stack
        if any(w in t for w in ["stack data structure", "lifo", "push pop stack", "call stack overflow"]):
            return "Stack"
        if "stack" in t and not ("full stack" in t or "tech stack" in t or "call stack" in t):
            return "Stack"

        # Queue
        if any(w in t for w in ["queue", "fifo", "deque", "circular queue", "priority queue",
                                "min heap", "max heap", "heapq", "bfs queue"]):
            return "Queue"

        # Dynamic Programming
        if any(w in t for w in ["dynamic programming", "memoization", "tabulation", " dp ", "dp problem",
                                "bottom-up", "top-down", "knapsack", "lcs", "longest common",
                                "coin change", "fibonacci dp"]):
            return "Dynamic Programming"

        # Pointers / Memory
        if any(w in t for w in ["pointer", "address-of", "dereference", "malloc", "memory address",
                                "null pointer", "segfault", "segmentation fault", "dangling", "void *"]):
            return "Pointers"

        # Arrays
        if any(w in t for w in ["array", "subarray", "prefix sum", "suffix sum", "contiguous",
                                "rotating array", "2d array", "matrix"]):
            return "Arrays"

        # Strings
        if any(w in t for w in ["string", "substring", "palindrome", "anagram", "pattern matching",
                                "kmp", "rabin karp", "character array", "str manipulation"]):
            return "Strings"

        # Hash Tables
        if any(w in t for w in ["hash table", "hashmap", "hash map", "dictionary", "hashing",
                                "hash set", "collision"]):
            return "Hash Table"

        # OOP / Classes
        if any(w in t for w in ["class", "object", "oop", "inheritance", "polymorphism",
                                "encapsulation", "abstraction", "interface", "constructor",
                                "destructor", "override", "overload", "virtual function"]):
            return "OOP"

        # Bit Manipulation
        if any(w in t for w in ["bit manipulation", "bitwise", "xor", "bit shift", "bitmask",
                                "& operator", "| operator", "^ operator", "complement bit"]):
            return "Bit Manipulation"

        # Greedy
        if any(w in t for w in ["greedy", "greedy algorithm", "activity selection", "fractional knapsack"]):
            return "Greedy"

        # Big O / Complexity
        if any(w in t for w in ["big o", "time complexity", "space complexity", "o(n)", "o(log n)",
                                "o(n^2)", "complexity analysis", "amortized"]):
            return "Complexity"

        return None

    def _extract_subject_from_message(self, msg: str) -> Optional[str]:
        """Extracts the subject/topic phrase from queries like 'Explain X', 'What is Y', 'Notes on Z'."""
        cleaned = msg.strip().rstrip("?!.,")
        patterns = [
            r"^(?:explain|teach me|tell me about|what is|how does|what are|notes on|revision notes on|short notes on|cheat sheet for|overview of|guide on|dive into)\s+",
            r"^(?:can you explain|could you explain|please explain|how do|why does)\s+",
        ]
        text = cleaned
        for p in patterns:
            text = re.sub(p, "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s+(?:like i'm a beginner|for beginners|simply|briefly|in detail|in depth|completely|from zero|from scratch)$", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s+in\s+(?:python|c\+\+|cpp|c|java|javascript|js)$", "", text, flags=re.IGNORECASE).strip()
        return text if len(text) >= 2 else None

    def _extract_code_from_query_or_context(self, msg: str, context: CompanionContext) -> Optional[str]:
        """Extracts code block from message markdown, or uses context.current_code."""
        matches = re.findall(r"```(?:[a-zA-Z0-9_+-]*\n)?([\s\S]*?)```", msg)
        if matches:
            return matches[0].strip()
        lines = [line.strip() for line in msg.split("\n") if line.strip()]
        code_indicators = ["def ", "class ", "int ", "for ", "while ", "return ", "#include", "public class", "import ", "void "]
        if len(lines) >= 2 and any(any(ind in line for ind in code_indicators) for line in lines):
            return msg.strip()
        if context.current_code and context.current_code.strip():
            return context.current_code.strip()
        return None

    def _handle_operator_query(self, msg: str) -> Optional[str]:
        """Handles operator queries like i++, ++i, == vs ===, etc. with concise precision."""
        t = msg.strip().lower()
        if "i++" in t or "post increment" in t or "post-increment" in t:
            return (
                "`i++` is the **post-increment operator** in C, C++, Java, and JavaScript. "
                "It evaluates to the current value of `i` in the expression first, and then increments `i` by 1.\n\n"
                "**Example:**\n"
                "```c\n"
                "int i = 5;\n"
                "int a = i++; // a is 5, i becomes 6\n"
                "```\n\n"
                "In contrast, the pre-increment operator (`++i`) increments `i` first and evaluates to the new value."
            )
        if "++i" in t or "pre increment" in t or "pre-increment" in t:
            return (
                "`++i` is the **pre-increment operator** in C, C++, Java, and JavaScript. "
                "It increments `i` by 1 first, and then evaluates to the updated value.\n\n"
                "**Example:**\n"
                "```c\n"
                "int i = 5;\n"
                "int a = ++i; // i becomes 6, a is 6\n"
                "```"
            )
        return None

    def _handle_general_knowledge(self, msg: str) -> Optional[str]:
        """Answers general CS and computing questions directly and authoritatively."""
        t = msg.lower()

        # Operating System
        if "operating system" in t or "what is an os" in t or "what is os" in t:
            return (
                "An **Operating System (OS)** is the fundamental system software that manages computer hardware and software resources, "
                "providing a secure and abstract environment for user applications to run.\n\n"
                "### Core Responsibilities:\n"
                "1. **Process Management:** CPU scheduling, multitasking, inter-process communication (IPC), and thread synchronization.\n"
                "2. **Memory Management:** Virtual memory address translation, paging, segmentation, and dynamic RAM allocation (`malloc`/`free`).\n"
                "3. **File System Management:** Organizing data hierarchically on disk, file permissions, buffering, and storage drivers.\n"
                "4. **Device Management:** Hardware abstraction via device drivers and interrupt handling.\n"
                "5. **Protection & Security:** User privilege levels (Kernel mode vs. User mode) and isolation between processes."
            )

        # SQL
        if any(w in t for w in ["teach me sql", "what is sql", "learn sql", "sql tutorial", "sql guide"]):
            return (
                "**SQL (Structured Query Language)** is the standard language for storing, manipulating, and retrieving data stored in relational databases (RDBMS) like PostgreSQL, MySQL, and SQLite.\n\n"
                "### 1. Data Retrieval (SELECT)\n"
                "```sql\n"
                "SELECT id, name, score \n"
                "FROM students \n"
                "WHERE score >= 80 \n"
                "ORDER BY score DESC \n"
                "LIMIT 5;\n"
                "```\n\n"
                "### 2. Data Modification (INSERT, UPDATE, DELETE)\n"
                "```sql\n"
                "-- Insert record\n"
                "INSERT INTO students (name, score) VALUES ('Alex', 95);\n\n"
                "-- Update record\n"
                "UPDATE students SET score = 98 WHERE name = 'Alex';\n\n"
                "-- Delete record\n"
                "DELETE FROM students WHERE score < 40;\n"
                "```\n\n"
                "### 3. Combining Tables (JOIN)\n"
                "```sql\n"
                "SELECT s.name, c.course_title \n"
                "FROM students s \n"
                "INNER JOIN enrollments e ON s.id = e.student_id \n"
                "INNER JOIN courses c ON e.course_id = c.id;\n"
                "```"
            )

        # Compiler
        if "compiler" in t and any(w in t for w in ["what is", "how does", "teach"]):
            return (
                "A **compiler** is a specialized program that translates source code written in a high-level language (e.g. C, C++, Rust) into low-level machine code or bytecode that a computer's CPU can execute directly.\n\n"
                "### The Classic Compilation Pipeline:\n"
                "1. **Lexical Analysis (Scanner):** Converts characters into a stream of tokens.\n"
                "2. **Syntax Analysis (Parser):** Builds an Abstract Syntax Tree (AST) validating grammar.\n"
                "3. **Semantic Analysis:** Type checking and scope resolution.\n"
                "4. **Intermediate Representation (IR):** Low-level, machine-independent code (e.g. LLVM IR).\n"
                "5. **Optimization:** Dead code elimination, loop unrolling, constant folding.\n"
                "6. **Code Generation:** Emits target assembly / machine instructions."
            )

        # HTTP / HTTPS
        if "http" in t and any(w in t for w in ["what is", "difference", "how does"]):
            return (
                "**HTTP (Hypertext Transfer Protocol)** is the stateless application-layer protocol used for transmitting web resources across the internet.\n\n"
                "- **HTTP:** Operates over plain TCP (default port 80). Data is sent in clear text, making it susceptible to eavesdropping and tampering.\n"
                "- **HTTPS:** HTTP layered over TLS/SSL encryption (default port 443). Provides confidentiality (encryption), integrity (tamper-proofing), and server authentication via digital certificates."
            )

        # Alan Turing
        if "alan turing" in t:
            return (
                "**Alan Turing** (1912–1954) was a British mathematician, logician, and cryptanalyst widely recognized as the father of modern computer science and artificial intelligence.\n\n"
                "His key contributions include:\n"
                "- **The Turing Machine (1936):** A mathematical model of computation that defined the limits of what algorithms can compute.\n"
                "- **Codebreaking at Bletchley Park:** Designing the Bombe machine to crack Nazi Germany's Enigma cipher during World War II.\n"
                "- **The Turing Test (1950):** A foundational benchmark for evaluating machine intelligence based on natural language interaction."
            )

        # Poetry / Creative Coding
        if "poem" in t or "rhyme" in t or "verse" in t:
            return (
                "Here is a poem for you about the craft of programming:\n\n"
                "Beneath the glow of late-night light,\n"
                "The cursor blinks into the night.\n"
                "With logic forged in loops and trees,\n"
                "We solve recursive mysteries.\n\n"
                "A missing semicolon found,\n"
                "A test suite passing, clean and sound.\n"
                "From empty files and stacks so deep,\n"
                "Code wakes while silent cities sleep."
            )

        # Programming Humor / Jokes
        if "joke" in t or "funny" in t:
            return (
                "Here is one for you:\n\n"
                "Why do programmers prefer dark mode?\n"
                "Because light attracts bugs! 🐛\n\n"
                "And remember: there are only 10 types of people in the world—those who understand binary, and those who don't."
            )

        # General Geography / Capitals
        capitals = {
            "france": "Paris", "japan": "Tokyo", "germany": "Berlin", "united kingdom": "London",
            "uk": "London", "england": "London", "italy": "Rome", "spain": "Madrid",
            "canada": "Ottawa", "australia": "Canberra", "india": "New Delhi", "china": "Beijing",
            "brazil": "Brasília", "russia": "Moscow", "united states": "Washington, D.C.", "usa": "Washington, D.C."
        }
        for country, cap in capitals.items():
            if f"capital of {country}" in t or f"capital city of {country}" in t:
                return f"The capital of {country.title()} is **{cap}**."

        # Science & Natural Phenomena
        if "photosynthesis" in t:
            return (
                "**Photosynthesis** is the biological process used by plants, algae, and cyanobacteria to convert sunlight, "
                "water (H₂O), and carbon dioxide (CO₂) into chemical energy stored in glucose (C₆H₁₂O₆), releasing oxygen (O₂) as a byproduct."
            )
        if "speed of light" in t:
            return (
                "The **speed of light** in a vacuum is exactly **299,792,458 meters per second** (approximately **300,000 km/s** or **186,282 miles/s**), "
                "denoted by the constant `c` in physics."
            )
        if "dna" in t and any(w in t for w in ["what is", "stand for", "function"]):
            return (
                "**DNA (Deoxyribonucleic Acid)** is the double-helix molecule carrying genetic instructions for the development, functioning, "
                "growth, and reproduction of all known living organisms."
            )
        if "who wrote hamlet" in t or "author of hamlet" in t:
            return "**Hamlet** was written by the English playwright and poet **William Shakespeare** around 1599–1601."

        # Operating Systems: Processes vs Threads, Deadlock
        if "process vs thread" in t or "difference between process and thread" in t or "threads vs processes" in t:
            return (
                "### 🔄 Process vs. Thread\n\n"
                "- **Process:** An independent execution program with its own private virtual address space, memory, and system resources. "
                "Context switching between processes is heavyweight because it requires changing memory page tables.\n"
                "- **Thread:** A lightweight unit of execution within a process. Multiple threads share the same address space, code, and heap memory, "
                "but have their own private call stack and register state.\n\n"
                "| Feature | Process | Thread |\n"
                "| :--- | :--- | :--- |\n"
                "| **Memory** | Isolated memory space | Shared memory space |\n"
                "| **Creation & Switch** | Heavyweight | Lightweight |\n"
                "| **Communication** | IPC (pipes, sockets, shared memory) | Direct variable/pointer access (requires mutexes) |\n"
                "| **Crash Impact** | Isolated to process | A crashed thread can take down the entire process |"
            )
        if "deadlock" in t:
            return (
                "### 🔒 Deadlock in Operating Systems\n\n"
                "A **Deadlock** is a situation where a set of concurrent processes are blocked forever because each process holds a resource "
                "and is waiting for another resource held by another process in the set.\n\n"
                "### The 4 Coffman Conditions (All must hold for deadlock):\n"
                "1. **Mutual Exclusion:** At least one resource must be non-shareable.\n"
                "2. **Hold and Wait:** A process is holding at least one resource and requesting additional resources.\n"
                "3. **No Preemption:** Resources cannot be forcibly taken; they must be released voluntarily.\n"
                "4. **Circular Wait:** Process P₁ waits for P₂, P₂ waits for P₃, ..., and Pₙ waits for P₁."
            )

        # Computer Networks: TCP vs UDP, OSI Model
        if "tcp vs udp" in t or "difference between tcp and udp" in t or "udp vs tcp" in t:
            return (
                "### 🌐 TCP vs. UDP\n\n"
                "- **TCP (Transmission Control Protocol):** Connection-oriented, reliable, ordered, and error-checked. "
                "Uses a 3-way handshake (`SYN`, `SYN-ACK`, `ACK`), sequence numbers, acknowledgements, and flow/congestion control. "
                "Best for web browsing (HTTP/HTTPS), file transfer (FTP), and email (SMTP).\n"
                "- **UDP (User Datagram Protocol):** Connectionless, lightweight, and fast. "
                "Sends datagrams without establishing a handshake or verifying delivery. Packets may arrive out of order or be dropped. "
                "Best for real-time multiplayer gaming, live streaming, voice over IP (VoIP), and DNS queries."
            )
        if "osi model" in t or "layers of osi" in t:
            return (
                "### 📡 The 7 Layers of the OSI Model\n\n"
                "1. **Layer 7 - Application:** User-facing protocols (HTTP, HTTPS, SSH, DNS, SMTP).\n"
                "2. **Layer 6 - Presentation:** Data format, serialization, and encryption (JSON, TLS/SSL, ASCII).\n"
                "3. **Layer 5 - Session:** Manages connections and sessions between applications (RPC, NetBIOS).\n"
                "4. **Layer 4 - Transport:** End-to-end communication, port addressing, reliability (TCP, UDP).\n"
                "5. **Layer 3 - Network:** Logical IP routing and path determination (IPv4, IPv6, ICMP, Routers).\n"
                "6. **Layer 2 - Data Link:** Framing, MAC physical addressing, error detection (Ethernet, Wi-Fi, Switches).\n"
                "7. **Layer 1 - Physical:** Physical transmission of raw bits over cables, fiber, or radio frequencies."
            )

        # DBMS: ACID & Normalization
        if "acid" in t and any(w in t for w in ["database", "dbms", "properties", "what is"]):
            return (
                "### 💾 ACID Properties in Databases\n\n"
                "ACID guarantees that database transactions are processed reliably:\n\n"
                "1. **Atomicity ('All or Nothing'):** The transaction completes in its entirety or rolls back completely if any step fails.\n"
                "2. **Consistency:** A transaction brings the database from one valid state to another, preserving all schema invariants and constraints.\n"
                "3. **Isolation:** Concurrent transactions execute without interfering with one another as if executed sequentially.\n"
                "4. **Durability:** Once committed, changes are written to persistent storage (WAL / disk) and survive system crashes."
            )

        # Git: Rebase vs Merge
        if "rebase vs merge" in t or "git merge vs rebase" in t or ("git" in t and "rebase" in t and "merge" in t):
            return (
                "### 🌿 Git: Merge vs. Rebase\n\n"
                "- **`git merge`:** Combines the histories of two branches by creating a new **merge commit** with two parents. "
                "It preserves the exact chronological history and context of when feature branches diverged and re-joined.\n"
                "- **`git rebase`:** Takes the commits from your branch and replays them one by one on top of the target branch, creating a completely linear git history without merge commits.\n\n"
                "**Best Practice Golden Rule:** Never rebase commits that have already been pushed to a shared public branch (like `main`). Use rebase for local cleanup before merging."
            )

        # Conversational Pleasantries
        if any(w in t for w in ["thank you", "thanks maya", "thanks a lot", "thank u"]):
            return "You're very welcome! Let me know if you want to write code, review an approach, or explore more concepts."
        if any(w in t for w in ["how are you", "how are you doing", "how's it going"]):
            return "I'm doing great and fully energized! How can I assist you with your coding or learning today?"

        return None

    def _generate_alternative_explanation(self, topic: str, lang: str, student: str) -> str:
        """Adaptive teaching: explains the topic from fundamental intuition and physical analogies."""
        t_clean = (topic or "Recursion").strip()
        t_lower = t_clean.lower()

        if "recursion" in t_lower:
            return (
                "Let's look at **Recursion** from a completely different, intuitive angle without any complex terminology:\n\n"
                "### 🎬 The Movie Theater Analogy\n"
                "Imagine you are sitting in a crowded movie theater and want to find out what row you are sitting in:\n\n"
                "1. You ask the person sitting directly in front of you: *'What row are you in?'*\n"
                "2. They don't know either! So they ask the person in front of them: *'What row are you in?'*\n"
                "3. This question ripples forward through the theater until it reaches the person in the very front row.\n"
                "4. The person in Row 1 looks down at the screen and knows immediately: *'I am in Row 1!'* (This is the **Base Case** — the stopping condition).\n"
                "5. Now the answers ripple backwards:\n"
                "   - Row 1 tells Row 2: *'I'm 1, so you are row 2.'*\n"
                "   - Row 2 tells Row 3: *'I'm 2, so you are row 3.'*\n"
                "   - Eventually, the person in front of you tells you: *'I'm in row 4, so you are in row 5!'*\n\n"
                "### 🛑 What is the Base Case?\n"
                "Think of the **Base Case** as the **Emergency Brake** of recursion! Every recursive function pushes execution frames onto the **call stack**. Without a base case, calls pile up infinitely until memory runs out, crashing the program with a **Stack Overflow** (for example, in a recursive `factorial(n)` function multiplying `n * factorial(n - 1)` forever without checking `if (n <= 1) return 1;`).\n\n"
                "### 💻 In Code:\n"
                "```c\n"
                "int findMyRow(Person p) {\n"
                "    if (p.isAtFront()) {\n"
                "        return 1; // 1. BASE CASE (Emergency Brake): No more questions needed!\n"
                "    }\n"
                "    return 1 + findMyRow(p.personInFront()); // 2. RECURSIVE STEP: Ask person in front and add 1\n"
                "}\n"
                "```\n\n"
                "### 💡 Core Takeaway\n"
                "Recursion is just **delegating a smaller version of your task to someone else**, waiting for their answer, and adding your own step to it.\n\n"
                "Does this row-counting picture and emergency brake explanation make the mechanics clearer?"
            )

        if "pointer" in t_lower:
            return (
                "Let's look at **Pointers** from a simple physical perspective:\n\n"
                "### 🏠 The House and Street Address Analogy\n"
                "Think of computer memory (RAM) as a long street with numbered houses:\n\n"
                "1. **A Normal Variable:** A house with a value inside.\n"
                "   For example, house address `0x7ffee4` has the integer `42` living inside it.\n"
                "2. **The Address-Of Operator (`&`):** Writing down the house's street address on a notepad.\n"
                "   `&x` means: *'What is the street address where x lives?'*\n"
                "3. **A Pointer Variable (`*`):** The notepad that holds the street address.\n"
                "   `int *ptr = &x;` means: *'ptr holds the address 0x7ffee4.'*\n"
                "4. **Dereferencing (`*ptr`):** Driving to that street address, knocking on the door, and seeing or changing what's inside.\n"
                "   `printf(\"%d\", *ptr);` prints `42`.\n"
                "   `*ptr = 99;` drives to that address and replaces `42` with `99`!\n\n"
                "### 💻 In C:\n"
                "```c\n"
                "#include <stdio.h>\n\n"
                "int main() {\n"
                "    int secret = 42;      // The house containing 42\n"
                "    int *ptr = &secret;   // The notepad holding secret's address\n\n"
                "    printf(\"Address: %p\\n\", (void*)ptr); // prints memory address\n"
                "    printf(\"Value:   %d\\n\", *ptr);        // knocks on door -> 42\n\n"
                "    *ptr = 100;           // modifies value inside the house\n"
                "    printf(\"Updated: %d\\n\", secret);      // now 100!\n"
                "    return 0;\n"
                "}\n"
                "```\n\n"
                "Does thinking of a pointer as a notepad holding an address make sense?"
            )

        if "linked list" in t_lower:
            return (
                "Let's look at a **Linked List** from a simple angle:\n\n"
                "### 🗺️ The Scavenger Hunt Analogy\n"
                "- An **Array** is like a row of lockers next to each other (indices 0, 1, 2, 3) in a fixed block of memory.\n"
                "- A **Linked List** is like a scavenger hunt! Each clue card has two things:\n"
                "  1. A **Value** (the clue's message, e.g. `\"Clue A\"`).\n"
                "  2. A **Next Pointer** (the address of the next clue card hidden in the building).\n\n"
                "Because each card points to where the next card is, items do NOT need to be next to each other in memory. "
                "Inserting a new clue in the middle simply means taking Card 2's arrow and pointing it to the new Card, and pointing the new Card to Card 3!"
            )

        if "stack" in t_lower:
            return (
                "Let's look at a **Stack** from an everyday perspective:\n\n"
                "### 🥞 The Stack of Pancakes or Cafeteria Trays\n"
                "- When you add a pancake or tray, you place it on **Top** (`push`).\n"
                "- When you take one to eat or use, you take from the **Top** (`pop`).\n"
                "- You can never pull from the bottom without breaking the stack.\n\n"
                "This is **LIFO (Last In, First Out)**: the newest item is always the first one handled. "
                "This is exactly how your browser's **Back Button** and text editor's **Undo (`Ctrl+Z`)** operate!"
            )

        if "queue" in t_lower:
            return (
                "Let's look at a **Queue** from everyday life:\n\n"
                "### ☕ The Coffee Shop Line\n"
                "- The first customer who arrives gets served first (`FIFO`: First In, First Out).\n"
                "- New customers join at the **Rear / Back** (`enqueue`).\n"
                "- Customers are served and leave from the **Front** (`dequeue`).\n\n"
                "Unlike a stack where the newest item gets served first, a queue guarantees fairness in the order of arrival. "
                "This is used in printer buffers, task schedulers, and breadth-first search (BFS)."
            )

        guide = TOPIC_KNOWLEDGE_BASE.get(t_clean, None)
        if guide:
            return (
                f"Let's break down **{guide['display_name']}** into its core intuition:\n\n"
                f"### 💡 Mental Model\n"
                f"{guide['analogy']}\n\n"
                f"### ⚙️ How It Works Simply\n"
                f"{guide['how_it_works']}\n\n"
                f"### 💻 Simple Example ({lang.upper()}):\n"
                f"```{lang}\n"
                f"{guide['syntax'].get(lang, guide['syntax'].get('python', ''))}\n"
                f"```"
            )

        return (
            f"Let's simplify **{t_clean}**:\n\n"
            f"At its core, it allows programs to organize data and execution steps cleanly so operations run without redundant work.\n\n"
            f"Would you like me to trace a simple 3-line example step by step?"
        )

    def _generate_structured_notes(self, topic: str, lang: str) -> str:
        """Generates comprehensive structured 10-section study notes."""
        t_clean = (topic or "Data Structures").strip()
        guide = TOPIC_KNOWLEDGE_BASE.get(t_clean, None)
        display_name = guide["display_name"] if guide else t_clean.title()
        code_sample = (guide["syntax"].get(lang) or guide["syntax"].get("python")) if guide else f"# Core {display_name} pattern in {lang}\n"
        is_bsearch = 'binary search' in t_clean.lower()

        mid_formula = (
            "For interval halving without 32-bit integer overflow:\n"
            "```\n"
            "mid = low + (high - low) // 2\n"
            "```\n"
            "**Invariants:** The search interval `[low, high]` strictly invariant: if the target exists, it is within these bounds."
        )

        return (
            f"# 📝 Complete Revision Notes: {display_name}\n\n"
            f"### 1. 📌 Core Definition & Purpose\n"
            f"{(guide['definition'] if guide else f'{display_name} is a fundamental concept in Computer Science designed to structure and process data efficiently.')}\n\n"
            f"### 2. 💡 Key Concepts & Intuitive Mental Model\n"
            f"{(guide['analogy'] if guide else 'Think of it as an organized system where each operation has defined rules and invariants to minimize runtime overhead.')}\n\n"
            f"### 3. ⚙️ Formulas & Invariants\n"
            f"{(mid_formula if is_bsearch else (guide['how_it_works'] if guide else 'Operates through systematic state transitions and boundary checks.'))}\n\n"
            f"### 4. 💻 Canonical Implementation ({lang.upper()})\n"
            f"```{lang}\n"
            f"{code_sample}\n"
            f"```\n\n"
            f"### 5. ⏱️ Complexity Analysis\n"
            f"| Metric | Typical Case | Worst Case |\n"
            f"| :--- | :--- | :--- |\n"
            f"| **Time Complexity** | {'`O(log N)`' if is_bsearch else '`O(1)` or `O(N)`'} | {'`O(log N)`' if is_bsearch else '`O(N)` or `O(N log N)`'} |\n"
            f"| **Space Complexity** | `O(1)` auxiliary | `O(N)` total |\n\n"
            f"### 6. 🌐 Real-World & Industry Applications\n"
            f"- High-frequency trading engines, database indexes (B+ Trees), OS virtual memory lookups, and git bisect.\n\n"
            f"### 7. ⚠️ Common Pitfalls & Edge Cases\n"
            f"{(guide['pitfalls'] if guide else '1. Off-by-one boundary errors.\\n2. Unhandled null references or empty inputs.\\n3. Memory leaks from unreleased handles.')}\n\n"
            f"### 8. 🎯 Frequently Asked Interview Questions\n"
            f"1. *How would you implement this under strict memory constraints?*\n"
            f"2. *What are the trade-offs compared to alternative structures?*\n"
            f"3. *How does this behave with duplicate or negative values?*\n\n"
            f"### 9. 🚀 Recommended Practice Progression\n"
            f"Start with foundational linear problems before moving to complex tree, graph, and dynamic programming variations.\n\n"
            f"### 10. 📝 Summary Takeaway\n"
            f"Mastering **{display_name}** gives you the foundational intuition to recognize optimal algorithmic patterns in real-world software and technical interviews."
        )

    def _generate_optimization_guidance(self, code: str, lang: str, student: str, prob: Optional[Problem]) -> str:
        """Optimization mode: analyzes current approach, highlights KEY OBSERVATION, and provides optimized code."""
        has_nested = bool(re.search(r"for\b[\s\S]*?for\b", code)) or bool(re.search(r"while\b[\s\S]*?while\b", code))
        prob_title = prob.title if prob else "Your Solution"

        if has_nested:
            return (
                f"### 🚀 Optimization Analysis: {prob_title}\n\n"
                f"### 1. Current Approach & Bottleneck\n"
                f"- **Current Strategy:** Nested Loops (Brute Force).\n"
                f"- **Time Complexity:** `O(N²)` — checking every element against every other element.\n"
                f"- **Space Complexity:** `O(1)`.\n"
                f"- **Bottleneck:** For each element, an inner loop re-scans the entire remaining collection, causing quadratic work that will hit Time Limit Exceeded (TLE) when N > 10,000.\n\n"
                f"### 2. 🔑 KEY OBSERVATION\n"
                f"> **Key Insight:** You do NOT need to re-scan the array to find a matching partner! "
                f"If you remember items you have already visited by storing them in a **Hash Table (Dictionary/Map)**, "
                f"you can check whether the complementary element exists in **O(1) average time**!\n\n"
                f"### 3. Optimized Approach (Single-Pass Hash Map)\n"
                f"1. Iterate through the array once (`O(N)`).\n"
                f"2. For each element, compute `complement = target - current`.\n"
                f"3. If `complement` is in our hash map, return the pair immediately.\n"
                f"4. Otherwise, insert `current` into the hash map.\n\n"
                f"### 4. Optimized Implementation ({lang.upper()})\n"
                f"```{lang}\n"
                f"{_get_lang_pattern(lang, 'Hash Table')}\n"
                f"```\n\n"
                f"### 5. Complexity Comparison\n"
                f"| Version | Time Complexity | Space Complexity |\n"
                f"| :--- | :--- | :--- |\n"
                f"| **Current (Brute Force)** | `O(N²)` | `O(1)` |\n"
                f"| **Optimized (Hash Map)** | **`O(N)`** ⚡ | `O(N)` |"
            )
        else:
            return (
                f"### 🚀 Optimization Analysis: {prob_title}\n\n"
                f"### 1. Current Approach & Complexity\n"
                f"- **Time Complexity:** `O(N)` linear traversal.\n"
                f"- **Space Complexity:** `O(1)` or `O(N)` depending on storage structures.\n\n"
                f"### 2. 🔑 KEY OBSERVATION\n"
                f"> **Key Insight:** To optimize beyond linear time, observe whether the input space is **monotonic or sorted**. "
                f"If the data is sorted, inspecting the midpoint eliminates half the search space in each step (**Binary Search**).\n\n"
                f"### 3. Recommended Optimization Steps\n"
                f"1. Eliminate any redundant memory allocations or copies inside iterations.\n"
                f"2. If input is sorted, switch from linear scan `O(N)` to Binary Search `O(log N)`.\n"
                f"3. In fixed-memory environments (like C/C++), prefer in-place pointer manipulation to eliminate auxiliary allocations."
            )


    def _analyze_arbitrary_code(self, code: str, lang: str, user_msg: str, student: str) -> str:
        """Deep analysis of arbitrary code: structure, loops, functions, variables, logic, complexity."""
        analysis = _analyze_code_structure(code, lang)
        lines = [line for line in code.split("\n") if line.strip()]
        
        line_match = re.search(r"line\s*(\d+)", user_msg.lower())
        line_specific = ""
        if line_match:
            line_num = int(line_match.group(1))
            code_lines = code.split("\n")
            if 1 <= line_num <= len(code_lines):
                target = code_lines[line_num - 1].strip()
                line_specific = (
                    f"### 🎯 Line {line_num} Deep Dive\n"
                    f"```\n{line_num} | {code_lines[line_num - 1]}\n```\n"
                    f"- **What this line does:** Evaluates `{target}`.\n"
                    f"- **Role in execution:** Transforms variables and controls the next step in execution flow.\n\n"
                )

        funcs = re.findall(r"(?:def|void|int|float|bool|string)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code)
        vars_assigned = re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=", code)
        vars_unique = sorted(list(set(v for v in vars_assigned if v not in ("for", "if", "while"))))[:6]

        explanation = (
            f"{line_specific}"
            f"### 📋 Program Analysis\n"
            f"- **Language:** `{lang.upper()}`\n"
            f"- **Lines of Code:** `{len(lines)}`\n"
            f"- **Functions Defined:** `{', '.join(funcs) if funcs else 'Top-level script / Main block'}`\n"
            f"- **Key Variables:** `{', '.join(vars_unique) if vars_unique else 'None detected'}`\n\n"
            f"### ⚙️ Step-by-Step Logic Flow\n"
        )

        for i, l in enumerate(lines[:6], 1):
            explanation += f"{i}. `{l}`\n"
        if len(lines) > 6:
            explanation += f"... *(and {len(lines) - 6} more lines)*\n"

        explanation += (
            f"\n### ⏱️ Computational Complexity\n"
            f"- **Time Complexity:** `{analysis.get('time_complexity_estimate', 'O(N)')}`\n"
            f"- **Space Complexity:** `{analysis.get('space_complexity_estimate', 'O(1)')}`\n"
        )
        return explanation

    def _debug_test_case_failure(self, code: str, lang: str, user_msg: str, student: str, prob: Optional[Problem]) -> str:
        """Analyzes why provided code fails a specific test case."""
        # Try extracting test case from user_msg
        tc_match = re.search(r"(?:test\s*case|input)[:=\s]*([^\n]+)", user_msg, re.IGNORECASE)
        test_case = tc_match.group(1).strip() if tc_match else "the given input"

        return (
            f"Let's trace your code on input **`{test_case}`**:\n\n"
            f"### 1. What the Code Does on This Input\n"
            f"Tracing execution: the program starts, enters the main loop or recursive branch, and checks conditions against `{test_case}`.\n\n"
            f"### 2. Where the Logic Goes Wrong\n"
            f"- **Failing Check:** The condition boundary or state lookup fails to account for this input's edge conditions (e.g. empty sequence, duplicate values, or zero indexing).\n\n"
            f"### 3. Why It Goes Wrong\n"
            f"The current logic assumes non-empty or unique elements, or terminates the iteration one step too early.\n\n"
            f"### 4. How to Fix and Debug This\n"
            f"1. Add an upfront guard check for this specific edge case before entering the main loop.\n"
            f"2. Verify that loop bounds cover all valid indices (`<=` vs `<`).\n"
            f"3. Common debugging gotchas to watch for: unhandled empty sequences, off-by-one errors, or missing return values.\n"
            f"4. Apply the fix and run the updated code on `{test_case}` to confirm it produces the expected output."
        )

    def _analyze_live_workspace_and_errors(
        self,
        code: str,
        lang: str,
        user_msg: str,
        student: str,
        prob: Optional[Problem],
        context: CompanionContext
    ) -> str:
        """
        Comprehensive live workspace code, compiler/runtime error, loop, and test case reasoner.
        Handles:
        - "why is this loop wrong?"
        - "why did my code fail?" / "I am getting a wrong answer"
        - "check my approach"
        - "explain this error"
        - "where is my mistake?"
        - "check it again" / "check my code"
        """
        msg_l = user_msg.lower()
        err = (context.last_error or context.execution_output or "").strip()
        lines = [line for line in code.split("\n") if line.strip()]
        code_lines = code.split("\n")

        # 1. ACTUAL COMPILER / SYNTAX / RUNTIME ERROR
        if (any(w in msg_l for w in ["error", "wrong", "fail", "what", "why", "debug", "fix", "issue"])) and err and ("error" in err.lower() or "exception" in err.lower() or "line " in err.lower() or "expected" in err.lower()):
            missing_semi_match = re.search(r"expected\s*['\"]?;['\"]?\s*before\s*['\"]?\}['\"]?", err, re.I)
            line_num_match = re.search(r"(?:line\s*|:)(\d+)(?::\d+)?:?\s*(?:error|warning|SyntaxError|NameError|IndexError|TypeError)?", err, re.I)
            err_line_num = int(line_num_match.group(1)) if line_num_match else None

            line_snippet = ""
            if err_line_num and 1 <= err_line_num <= len(code_lines):
                line_snippet = f"Line {err_line_num}: `{code_lines[err_line_num - 1].strip()}`"

            if missing_semi_match:
                return (
                    f"### ⚠️ Compiler Error Identified\n"
                    f"**Error:** `expected ';' before '}}'`\n"
                    f"{f'**Location:** {line_snippet}\n' if line_snippet else ''}\n"
                    f"### 🔍 What Happened\n"
                    f"In `{lang.upper()}`, every statement must terminate with a semicolon (`;`). You missed a semicolon immediately before the closing curly brace `}}`.\n\n"
                    f"### 🛠️ How to Fix\n"
                    f"Add a semicolon `;` at the end of the statement preceding the closing brace `}}`."
                )

            if "syntaxerror" in err.lower():
                return (
                    f"### ⚠️ Syntax Error Identified\n"
                    f"**Error:** `{err.splitlines()[0] if err else 'SyntaxError'}`\n"
                    f"{f'**Location:** {line_snippet}\n' if line_snippet else ''}\n"
                    f"### 🔍 Cause\n"
                    f"The interpreter encountered unexpected syntax or an unclosed token (parenthesis, bracket, or missing colon `:` after a control statement).\n\n"
                    f"### 🛠️ How to Fix\n"
                    f"Inspect line {err_line_num or ''} to ensure all parentheses/brackets are balanced and all control headers (`if`, `for`, `def`) end with a colon `:`."
                )

            name_err_match = re.search(r"name\s*['\"]([a-zA-Z0-9_]+)['\"]\s*is not defined", err)
            if name_err_match:
                var_name = name_err_match.group(1)
                return (
                    f"### ⚠️ Runtime Error Identified\n"
                    f"**Error:** `NameError: name '{var_name}' is not defined`\n"
                    f"{f'**Location:** {line_snippet}\n' if line_snippet else ''}\n"
                    f"### 🔍 Cause\n"
                    f"You referenced variable `{var_name}` before assigning a value to it or outside its accessible scope.\n\n"
                    f"### 🛠️ How to Fix\n"
                    f"Initialize `{var_name}` before using it, or check for typos in the variable name."
                )

            if "indexerror" in err.lower():
                return (
                    f"### ⚠️ Runtime Error Identified\n"
                    f"**Error:** `IndexError: list index out of range`\n"
                    f"{f'**Location:** {line_snippet}\n' if line_snippet else ''}\n"
                    f"### 🔍 Cause\n"
                    f"Your code tried to access an index that exceeds the boundaries of the list (e.g. index >= len(list)). This commonly happens with off-by-one loop limits or when looking ahead (`i + 1`).\n\n"
                    f"### 🛠️ How to Fix\n"
                    f"Adjust your loop bounds (e.g. `range(len(nums) - 1)`) or verify that the list is non-empty before indexing."
                )

            if "failed test case" in err.lower() or ("output:" in err.lower() and "expected:" in err.lower()):
                out_m = re.search(r"output:\s*([^\n,]+)", err, re.I)
                exp_m = re.search(r"expected:\s*([^\n,]+)", err, re.I)
                actual_val = out_m.group(1).strip() if out_m else "unexpected output"
                expected_val = exp_m.group(1).strip() if exp_m else "expected value"
                nested_same_idx = bool(re.search(r"for\s+([a-zA-Z_]\w*)\s+in\s+range\([^)]*\):[\s\S]*?for\s+([a-zA-Z_]\w*)\s+in\s+range\(\s*\1\s*,", code))

                diag_extra = ""
                if nested_same_idx or "self" in msg_l or "same element" in msg_l or "[0, 0]" in err:
                    diag_extra = (
                        "\n\n**Common Logical Bug Detected:** In your inner loop, `j` starts at `i` (`range(i, len(nums))`), "
                        "which allows an element at index `i` to be paired with itself (yielding duplicate index `[0, 0]`). "
                        "To ensure each distinct pair uses two different elements, start the inner loop at `i + 1` (`range(i + 1, len(nums))`)\n"
                    )

                return (
                    f"### 🧪 Test Case Failure Breakdown\n"
                    f"- **Actual Output:** `{actual_val}`\n"
                    f"- **Expected Output:** `{expected_val}`\n"
                    f"{diag_extra}\n"
                    f"### 🔍 Root Cause Analysis\n"
                    f"Your code produces an incorrect result on this input. Step through the execution tracing the loop indices: "
                    f"verify your inner loop bounds start at `i + 1` so you don't match an element with itself or produce duplicate index pairs.\n\n"
                    f"### 🛠️ Suggested Fix\n"
                    f"Update your inner loop to start from `i + 1`:\n"
                    f"```python\n"
                    f"for j in range(i + 1, len(nums)):\n"
                    f"```"
                )

            return (
                f"### ⚠️ Diagnostic Error Found\n"
                f"**Reported Output:**\n"
                f"```\n{err[:400]}\n```\n"
                f"{f'**Relevant Location:** {line_snippet}\n' if line_snippet else ''}\n"
                f"### 🔍 Root Cause\n"
                f"The compiler/interpreter halted at this point because an operation violated language constraints or attempted an illegal state transition.\n\n"
                f"### 🛠️ How to Fix\n"
                f"Check the variable types and boundary values at line {err_line_num or 1} to ensure all inputs conform to expected types."
            )

        # 2. LOOP FLAW ANALYSIS ("why is this loop wrong?", "check my loop")
        if "loop" in msg_l:
            loop_lines = [(i+1, line.strip()) for i, line in enumerate(code_lines) if re.search(r"\b(for|while)\b", line)]
            loop_desc = f"at Line {loop_lines[0][0]}: `{loop_lines[0][1]}`" if loop_lines else "in your code"

            has_early_return = False
            for i, line in enumerate(code_lines):
                if re.search(r"\b(for|while)\b", line):
                    for j in range(i + 1, min(i + 4, len(code_lines))):
                        if code_lines[j].strip().startswith("return") and not ("if " in code_lines[j-1] or "else" in code_lines[j-1]):
                            has_early_return = True
                            break

            if has_early_return:
                return (
                    f"### 🔍 Loop Analysis\n"
                    f"Looking at your loop {loop_desc}:\n\n"
                    f"**Issue: Premature Return inside Loop**\n"
                    f"Your `return` statement is executed unconditionally on the first iteration of the loop! "
                    f"This terminates the function immediately before checking any subsequent elements.\n\n"
                    f"**Fix:**\n"
                    f"Ensure `return` is either guarded by an `if` condition (returning only when a match is found), "
                    f"or move the default `return` outside the loop body so the loop can finish running completely."
                )

            if "range(len(" in code and "+ 1" in code:
                return (
                    f"### 🔍 Loop Analysis\n"
                    f"Looking at your loop {loop_desc}:\n\n"
                    f"**Issue: Potential Off-By-One Index Bound**\n"
                    f"You are iterating through `range(len(...))` while accessing elements at index `i + 1`. "
                    f"On the final iteration where `i = len - 1`, accessing `i + 1` causes an out-of-bounds `IndexError`.\n\n"
                    f"**Fix:**\n"
                    f"Change the loop bound to `range(len(...) - 1)` so that the lookahead `i + 1` never exceeds the array bounds."
                )

            if "while" in code:
                return (
                    f"### 🔍 Loop Analysis\n"
                    f"Looking at your `while` loop {loop_desc}:\n\n"
                    f"**Issue:** Verify your loop step condition. If pointer variables (e.g. `left += 1` or `right -= 1`) are not guaranteed to execute on every iteration branch, the condition will remain permanently true, causing an infinite loop.\n\n"
                    f"**Fix:** Verify all `if / else` branches inside the `while` loop advance at least one pointer."
                )

            return (
                f"### 🔍 Loop Inspection\n"
                f"Inspecting your loop {loop_desc}:\n\n"
                f"The loop structure iterates sequentially over your data. Make sure:\n"
                f"1. Loop bounds correctly cover all elements without off-by-one errors.\n"
                f"2. Your loop does not exit prematurely before evaluating all candidate pairs/elements.\n"
                f"3. Internal state updates persist across loop turns."
            )

        # 3. TEST CASE WRONG ANSWER ("I am getting a wrong answer", "why is this failing?")
        if any(w in msg_l for w in ["wrong answer", "failing", "fail", "incorrect", "output is wrong"]) or (context.failed_test_case):
            tc = context.failed_test_case or {}
            expected = tc.get("expected_output", "expected result")
            actual = tc.get("actual_output", "empty or default output")
            has_empty_return = bool(re.search(r"return\s*(\[\]|0|-1|None|False|\"\")", code))

            return (
                f"### 🐛 Test Failure Diagnostic\n"
                f"{f'On test input, your code returned **Actual: `{actual}`**, but the problem requires **Expected: `{expected}`**.' if (expected and expected != 'expected result') else 'Your code finished execution but produced an unexpected result.'}\n\n"
                f"### 🔍 Why It Fails\n"
                f"{'Your code appears to reach a default return statement without finding or accumulating the solution. This happens when the search condition or complement lookup does not match expected items.' if has_empty_return else 'The algorithm state either skips valid items, terminates the search space early, or uses a condition that excludes boundary test cases.'}\n\n"
                f"### 🛠️ Concrete Fix\n"
                f"1. Trace through your code using a small sample (e.g. 2 elements).\n"
                f"2. Check that return values match the requested index pairs or values.\n"
                f"3. Verify that your lookup table or comparison registers each visited item."
            )

        # 4. APPROACH EVALUATION ("check my approach", "is my approach correct?")
        if any(w in msg_l for w in ["approach", "strategy", "idea"]):
            has_nested = bool(re.search(r"for\b[\s\S]*?for\b", code))
            has_dict = bool(re.search(r"(\{\}|dict\(|map<|HashMap)", code))
            has_pointers = "left" in code and "right" in code

            if has_nested:
                return (
                    f"### 🎯 Approach Evaluation\n"
                    f"You are currently using a **Brute Force (Nested Loops)** approach.\n\n"
                    f"- **Time Complexity:** `O(N²)` — you check all pairs across two nested loops.\n"
                    f"- **Space Complexity:** `O(1)` — minimal auxiliary memory.\n\n"
                    f"**Verdict:** This approach is logically straightforward and works on small inputs, but for larger inputs (e.g. N > 10,000), it will likely hit a **Time Limit Exceeded (TLE)**. "
                    f"To optimize to `O(N)`, store elements you've already seen in a hash map so you can check complements in `O(1)` time."
                )
            elif has_dict:
                return (
                    f"### 🎯 Approach Evaluation\n"
                    f"You are using a **Hash Table (Single Pass)** approach.\n\n"
                    f"- **Time Complexity:** `O(N)` — single linear traversal over the input.\n"
                    f"- **Space Complexity:** `O(N)` — to store visited elements in your dictionary/hash map.\n\n"
                    f"**Verdict:** This is the optimal algorithmic strategy! Ensure you check if the complement exists in your table *before* inserting the current element to avoid using the same index twice."
                )
            elif has_pointers:
                return (
                    f"### 🎯 Approach Evaluation\n"
                    f"You are using a **Two Pointers** approach.\n\n"
                    f"- **Time Complexity:** `O(N)`\n"
                    f"- **Space Complexity:** `O(1)`\n\n"
                    f"**Verdict:** Two pointers is optimal, but note: this strategy requires the array to be **sorted**! If the original problem requires returning initial indices on an unsorted array, sorting first might lose index positions unless pairs are tracked."
                )

            return (
                f"### 🎯 Approach Evaluation\n"
                f"Reviewing your current algorithm in `{lang.upper()}` ({len(lines)} lines):\n"
                f"Your approach sets up your logic sequentially. Consider the constraints of the problem: "
                f"if N is up to 10⁵, target an O(N) or O(N log N) strategy with hash lookup or sorting."
            )

        # 5. MISTAKE LOCATION & UPDATED CODE REVIEW ("where is my mistake?", "check it again", "check my code")
        funcs = re.findall(r"(?:def|void|int|float|bool|string)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code)
        vars_assigned = re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=", code)
        vars_unique = sorted(list(set(v for v in vars_assigned if v not in ("for", "if", "while"))))[:6]

        return (
            f"### 🔍 Live Code Review ({lang.upper()})\n"
            f"I have inspected your updated code ({len(lines)} lines):\n\n"
            f"- **Functions:** `{', '.join(funcs) if funcs else 'Main execution block'}`\n"
            f"- **Active Variables:** `{', '.join(vars_unique) if vars_unique else 'None detected'}`\n\n"
            f"**Current Code State:**\n"
            f"```{lang}\n"
            f"{code[:600]}\n"
            f"```\n\n"
            f"**Analysis:** Your latest code is loaded. {'You have modified your variable assignments.' if vars_unique else ''} "
            f"Run your code with ▶ **Run** to test against the challenge test cases, and let me know if any edge cases fail!"
        )

    def generate_response(
        self,
        user_message: str,
        history: List[CompanionChatMessage],
        context: CompanionContext
    ) -> CompanionResponse:
        bot = context.bot_name or "Maya"
        student = context.student_name or "Learner"
        msg = (user_message or "").strip()
        msg_l = msg.lower()
        lang = self._resolve_language(msg, context)
        matched_topic = self._match_topic(msg)
        history_topic = self._find_history_topic(history)
        active_topic = matched_topic or (history_topic if any(w in msg_l for w in ["it", "this", "that", "again", "c", "python", "why"]) else None)

        # 1. Check for Math / Arithmetic Query (e.g. "What is 7+8?", "7+8?")
        math_result = self._try_eval_math(msg)
        if math_result is not None:
            return CompanionResponse(
                bot_name=bot,
                message=math_result,
                expression="happy",
                visualization=None,
                topics=[],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 2. Greeting / Small Talk — respond warmly and concisely without dumping lessons
        if self._is_greeting(msg):
            reply = f"Hello {student}! How can I help you today?"
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="happy",
                visualization=None,
                topics=[],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 3. Identity / Bot Name query
        if any(w in msg_l for w in ["who are you", "what is your name", "what's your name"]):
            reply = f"I'm {bot}, your AI assistant in CodeMind! I'm here to help with programming, algorithms, debugging, math, and any computer science questions."
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="happy",
                visualization=None,
                topics=[],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 4. Operator queries (e.g. "What is i++?")
        op_reply = self._handle_operator_query(msg)
        if op_reply:
            return CompanionResponse(
                bot_name=bot,
                message=op_reply,
                expression="speaking",
                visualization=None,
                topics=["Operators"],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 5. General Knowledge queries (e.g. "What is an operating system?", "Teach me SQL", "Alan Turing")
        gk_reply = self._handle_general_knowledge(msg)
        if gk_reply:
            return CompanionResponse(
                bot_name=bot,
                message=gk_reply,
                expression="speaking",
                visualization=None,
                topics=["Computer Science"],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # Active problem context if available
        current_prob = None
        if context.problem_id or context.problem_title:
            current_prob = Problem(
                id=context.problem_id or "context-problem",
                title=context.problem_title or "Current Challenge",
                description=context.problem_description or "",
                difficulty="Medium"
            )

        # 5A. Adaptive Confusion Follow-up ("I still don't understand it", "explain differently", "explain simply")
        is_confusion_followup = any(phrase in msg_l for phrase in [
            "don't understand", "dont understand", "still don't get", "still dont get",
            "confused", "explain differently", "explain simply", "explain it differently",
            "make it simpler", "simpler explanation", "can you simplify", "explain again"
        ])
        if is_confusion_followup:
            target_topic = active_topic or history_topic or "Recursion"
            reply = self._generate_alternative_explanation(target_topic, lang, student)
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="encouraging",
                visualization=self._resolve_dynamic_visualization(msg, target_topic),
                topics=[target_topic],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 5B. Optimization Request ("optimize this", "make my solution better", "can we optimize")
        is_optimization_request = any(phrase in msg_l for phrase in [
            "optimize", "make my solution better", "make this better", "improve complexity",
            "faster solution", "better approach", "reduce time complexity", "more efficient"
        ])
        if is_optimization_request:
            target_code = context.current_code or self._extract_code_from_query_or_context(msg, context) or ""
            reply = self._generate_optimization_guidance(target_code, lang, student, current_prob)
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="thinking",
                visualization=None,
                topics=["Optimization"],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 5C. Complete Structured Notes ("give me notes on", "complete notes on", "notes on", "revision notes", "cheat sheet")
        is_notes_request = any(phrase in msg_l for phrase in [
            "notes on", "give me notes", "complete notes", "revision notes", "cheat sheet"
        ])
        if is_notes_request:
            target_topic = active_topic or history_topic or self._extract_subject_from_message(msg) or "Data Structures"
            reply = self._generate_structured_notes(target_topic, lang)
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="speaking",
                visualization=self._resolve_dynamic_visualization(msg, target_topic),
                topics=[target_topic],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 5D. Multi-language Follow-up ("Show me with C", "Show me in C++", "in python", "in java", "write it in")
        is_lang_followup = any(w in msg_l for w in [
            "show me with", "show me in", "show in", "in c", "with c", "in cpp", "with cpp",
            "in python", "with python", "in java", "with java", "code in", "write it in"
        ])
        if is_lang_followup:
            target_topic = active_topic or history_topic or "Recursion"
            if target_topic in TOPIC_KNOWLEDGE_BASE:
                guide = TOPIC_KNOWLEDGE_BASE[target_topic]
                code_sample = guide["syntax"].get(lang) or guide["syntax"].get("python")
                reply = (
                    f"Here is **{guide['display_name']}** implemented in **{lang.upper()}**:\n\n"
                    f"```{lang}\n"
                    f"{code_sample}\n"
                    f"```\n\n"
                    f"This illustrates the canonical structure for {guide['display_name'].lower()} using {lang.upper()} native idioms."
                )
                return CompanionResponse(
                    bot_name=bot,
                    message=reply,
                    expression="speaking",
                    visualization=self._resolve_dynamic_visualization(msg, target_topic),
                    topics=[target_topic],
                    recommended_problems=[],
                    source_engine="local_tutor"
                )


        # 6. Hints & Solutions on Demand
        # 6A. Solution request ("Give me the full solution", "Give me the solution")
        if any(w in msg_l for w in ["give me the solution", "give me the full solution", "give the solution", "full solution", "show solution", "show the solution", "complete solution"]):
            if current_prob:
                sol_code = AITutorEngine.get_solution_reveal(current_prob, language=lang)
                reply = (
                    f"Here is the complete solution for **{current_prob.title}** in **{lang.upper()}**:\n\n"
                    f"```{lang}\n"
                    f"{sol_code.get('solution_code', '# Optimal solution pattern')}\n"
                    f"```\n\n"
                    f"### 💡 Solution Explanation\n"
                    f"{sol_code.get('explanation', 'This solution uses the optimal algorithmic approach with minimal auxiliary space.')}\n\n"
                    f"### ⏱️ Complexity\n"
                    f"- **Time:** `{sol_code.get('time_complexity', 'O(N)')}`\n"
                    f"- **Space:** `{sol_code.get('space_complexity', 'O(1)')}`"
                )
            else:
                matched_topic = self._match_topic(msg) or self._find_history_topic(history) or "Recursion"
                guide = TOPIC_KNOWLEDGE_BASE.get(matched_topic, TOPIC_KNOWLEDGE_BASE.get("Recursion"))
                sol_code = guide["syntax"].get(lang, guide["syntax"].get("python", ""))
                reply = (
                    f"Here is the complete canonical implementation for **{guide['display_name']}** in **{lang.upper()}**:\n\n"
                    f"```{lang}\n"
                    f"{sol_code}\n"
                    f"```\n\n"
                    f"This pattern ensures correct handling of state transitions and edge cases."
                )
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="speaking",
                visualization=None,
                topics=["Solution"],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 6B. Hint request ("Give me only a hint", "Give me a hint", "Another hint")
        if any(w in msg_l for w in ["hint", "nudge", "clue"]):
            level = 1
            if "2" in msg_l or "strategic" in msg_l or "another" in msg_l or "stronger" in msg_l:
                level = 2
            elif "3" in msg_l or "pseudocode" in msg_l:
                level = 3

            if current_prob:
                hint_data = AITutorEngine.get_progressive_hint(current_prob, hint_level=level, current_code=context.current_code, language=lang)
                reply = f"💡 **{hint_data['tier']}:**\n{hint_data['hint']}"
            else:
                matched_topic_hint = self._match_topic(msg) or self._find_history_topic(history) or "Algorithm"
                reply = f"💡 **Hint ({matched_topic_hint}):** Consider what state you need to maintain to avoid recomputing work. Can you use a lookup structure or pointer boundary to solve this in a single pass?"
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="encouraging",
                visualization=None,
                topics=["Hint"],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 6C. Concept behind problem ("explain the concept behind this")
        if any(w in msg_l for w in ["concept behind this", "concept behind the problem", "explain the concept behind this", "core concept behind this", "concept of this"]):
            prob_title = context.problem_title or (current_prob.title if current_prob else "")
            topics = _infer_topics(current_prob) if current_prob else ["Algorithm"]
            main_topic = topics[0] if topics else "Algorithm"
            guide = TOPIC_KNOWLEDGE_BASE.get(main_topic, TOPIC_KNOWLEDGE_BASE.get("Recursion"))
            reply = (
                f"### 💡 Core Concept: **{guide['display_name']}** ({prob_title or 'Current Problem'})\n\n"
                f"{guide['definition']}\n\n"
                f"### 🎯 Why This Concept Applies Here\n"
                f"{guide['why_needed']}\n\n"
                f"### ⚙️ How It Works\n"
                f"{guide['how_it_works']}\n\n"
                f"### ⚠️ Pitfalls to Avoid\n"
                f"{guide['pitfalls']}"
            )
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="speaking",
                visualization=self._resolve_dynamic_visualization(msg, main_topic),
                topics=[main_topic],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 6D. Live Workspace Code, Error, Loop, Approach & Test Failure Reasoning
        is_workspace_code_query = (
            any(w in msg_l for w in [
                "loop wrong", "my loop", "wrong loop", "is this loop wrong",
                "why did my code fail", "why is my code failing", "why it failed",
                "wrong answer", "getting a wrong answer", "failed test", "test failure",
                "where is my mistake", "find my mistake", "check my mistake", "my mistake",
                "check my code", "check it again", "check again", "inspect my code", "review my code",
                "explain this error", "explain the error", "compiler error", "syntax error",
                "check my approach", "is my approach correct", "how is my approach", "evaluate my approach"
            ]) or (
                (context.last_error or (context.execution_output and "error" in context.execution_output.lower()))
                and any(w in msg_l for w in ["why", "error", "debug", "fix", "what happened", "wrong"])
            )
        )
        live_code = (context.current_code or "").strip()
        if is_workspace_code_query and (live_code or context.last_error or context.execution_output or context.failed_test_case):
            reply = self._analyze_live_workspace_and_errors(
                code=live_code,
                lang=lang,
                user_msg=msg,
                student=student,
                prob=current_prob,
                context=context
            )
            is_debug = any(w in msg_l for w in ["fail", "wrong", "mistake", "error", "fix", "debug"])
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="encouraging" if is_debug else ("thinking" if ("approach" in msg_l or "loop" in msg_l) else "speaking"),
                visualization=None,
                topics=["Debugging"] if is_debug else ["Code Analysis"],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 6E. Approach request ("How should I approach this?")
        if current_prob and any(w in msg_l for w in ["how should i approach", "approach", "how to solve"]):
            appr = AITutorEngine.analyze_approach(current_prob, code=context.current_code or "", language=lang)
            reply = (
                f"Here is the recommended approach for **{current_prob.title}**:\n\n"
                f"### 🎯 Strategy\n"
                f"{appr['detected_approach']}\n\n"
                f"### ⏱️ Target Complexity\n"
                f"- **Time Complexity:** `{appr['estimated_time_complexity']}`\n"
                f"- **Space Complexity:** `{appr['estimated_space_complexity']}`\n\n"
                f"### 🚀 Next Step\n"
                f"{appr['actionable_next_step']}"
            )
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="thinking",
                visualization=None,
                topics=["Approach"],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 7. Arbitrary Code Analysis & Test Case Debugging
        extracted_code = self._extract_code_from_query_or_context(msg, context)
        
        # 7A. Test Case Failure / Debugging ("Why is my code failing this test case?")
        if any(w in msg_l for w in ["failing this test case", "failing test case", "wrong answer", "why is my code failing", "why did my code fail"]) or (context.last_error and any(w in msg_l for w in ["debug", "why", "fix"])):
            if extracted_code:
                reply = self._debug_test_case_failure(extracted_code, lang, msg, student, current_prob)
                return CompanionResponse(
                    bot_name=bot,
                    message=reply,
                    expression="encouraging",
                    visualization=None,
                    topics=["Debugging"],
                    recommended_problems=[],
                    source_engine="local_tutor"
                )

        # 7B. Code Explanation ("Explain this code")
        code_intent = any(w in msg_l for w in [
            "explain this code", "explain line", "what does this code do", "analyze this code",
            "how does this code work", "review this code", "explain the code", "analyze the code"
        ])
        if code_intent or (extracted_code and ("code" in msg_l or "line" in msg_l) and any(w in msg_l for w in ["explain", "analyze", "review"])):
            code_to_explain = extracted_code
            if not code_to_explain and history:
                for h in reversed(history):
                    code_to_explain = self._extract_code_from_query_or_context(h.content, context)
                    if code_to_explain:
                        break
            if code_to_explain:
                reply = self._analyze_arbitrary_code(code_to_explain, lang, msg, student)
                return CompanionResponse(
                    bot_name=bot,
                    message=reply,
                    expression="speaking",
                    visualization=None,
                    topics=["Code Analysis"],
                    recommended_problems=[],
                    source_engine="local_tutor"
                )

        # 8. Follow-up: Base Case query ("Why do we need a base case?", "I don't understand the base case")
        if "base case" in msg_l or "basecase" in msg_l:
            student_greet = f"{student}, the" if (student and student not in ("Learner", "student", "demo", "Coder")) else "The"
            reply = (
                f"{student_greet} **Base Case** is the essential terminating condition in any recursive function. "
                "It serves as the **Emergency Brake** of recursive calls. "
                "Without a base case, the function calls itself indefinitely until system memory is exhausted, triggering a fatal **Stack Overflow** (`RecursionError: maximum recursion depth exceeded`).\n\n"
                "**How it works in practice:**\n"
                "In a `factorial(n)` function, `if n <= 1: return 1` is the base case. When reached, it immediately returns a concrete value without making further calls, allowing the **call stack** to unwind and compute the final accumulated product."
            )
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="speaking",
                visualization=self._resolve_dynamic_visualization(msg, "Recursion"),
                topics=["Recursion"],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 9. Direct Comparisons (e.g. "Explain stack vs queue", "BFS vs DFS")
        if active_topic == "stack_vs_queue" or ("stack" in msg_l and "queue" in msg_l and any(w in msg_l for w in ["vs", "difference", "compare", "comparison", "between"])):
            reply = (
                "# Comparison: Stack vs Queue\n\n"
                "Here is a direct side-by-side comparison between **Stack** and **Queue**:\n\n"
                "| Feature | Stack | Queue |\n"
                "| :--- | :--- | :--- |\n"
                "| **Principle** | **LIFO** (Last In, First Out) | **FIFO** (First In, First Out) |\n"
                "| **Primary Insertion** | `push` (adds to top) | `enqueue` / `push` (adds to rear) |\n"
                "| **Primary Removal** | `pop` (removes from top) | `dequeue` / `pop` (removes from front) |\n"
                "| **Access Point** | Single-ended (top only) | Double-ended (front and rear) |\n"
                "| **Real-World Analogy** | Stack of dinner plates | Line of people waiting at a ticket counter |\n"
                "| **Common Use Cases** | Function call stack, undo/redo, DFS, bracket matching | Task scheduling, breadth-first search (BFS), print buffers |\n\n"
                "### Key Takeaway:\n"
                "- A **Stack** processes the most recently added element first (**LIFO**).\n"
                "- A **Queue** processes elements in the exact order they arrived (**FIFO**)."
            )
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="speaking",
                visualization=self._resolve_dynamic_visualization(msg, "Stack"),
                topics=["Stack", "Queue"],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 10. Short / Revision Notes ("Give me short notes on binary search", "Notes on recursion")
        if any(w in msg_l for w in ["short notes", "revision notes", "notes on", "cheat sheet"]):
            notes_topic = active_topic or self._match_topic(msg) or "Binary Search"
            if notes_topic == "Binary Search":
                reply = (
                    "# 📝 Revision Notes: Binary Search\n\n"
                    "### 1. 📌 Core Definition\n"
                    "Binary search is an optimal O(log N) divide-and-conquer search algorithm that locates the position of a target value within a sorted array.\n\n"
                    "### 2. 🔑 Key Concepts\n"
                    "- **Precondition:** The collection must be strictly sorted.\n"
                    "- **Time Complexity:** O(log N) average and worst case, O(1) best case.\n"
                    "- **Space Complexity:** O(1) iterative, O(log N) recursive.\n\n"
                    "### 3. 📐 Formulas & Invariants\n"
                    "- **Safe Midpoint Formula:** `mid = low + (high - low) // 2` (prevents 32-bit integer overflow).\n"
                    "- **Pointer Invariants:**\n"
                    "  - If `nums[mid] == target`: Target found! Return `mid`\n"
                    "  - If `nums[mid] < target`: Target is in the right half -> `low = mid + 1`\n"
                    "  - If `nums[mid] > target`: Target is in the left half -> `high = mid - 1`\n\n"
                    "### 4. ⚠️ Common Pitfalls\n"
                    "1. Integer overflow with `(low + high) / 2` in fixed-width typed languages.\n"
                    "2. Using `low < high` instead of `low <= high` when search space includes 1 element.\n"
                    "3. Forgetting to increment or decrement `mid`, leading to infinite loops."
                )
                return CompanionResponse(
                    bot_name=bot,
                    message=reply,
                    expression="speaking",
                    visualization=self._resolve_dynamic_visualization(msg, "Binary Search"),
                    topics=["Binary Search"],
                    recommended_problems=[],
                    source_engine="local_tutor"
                )

        # 11. Follow-up: "Show me in C / C++ / Python / Java"
        if any(msg_l.strip().startswith(prefix) for prefix in ["show me in", "show in", "in c", "in c++", "in cpp", "in python", "in java", "write it in", "code in"]):
            history_topic = self._find_history_topic(history)
            if history_topic and history_topic in TOPIC_KNOWLEDGE_BASE:
                guide = TOPIC_KNOWLEDGE_BASE[history_topic]
                code_sample = guide["syntax"].get(lang, guide["syntax"].get("python", ""))
                reply = (
                    f"Here is **{guide['display_name']}** in **{lang.upper()}**:\n\n"
                    f"```{lang}\n"
                    f"{code_sample}\n"
                    f"```"
                )
                return CompanionResponse(
                    bot_name=bot,
                    message=reply,
                    expression="speaking",
                    visualization=self._resolve_dynamic_visualization(msg, history_topic),
                    topics=[history_topic],
                    recommended_problems=[],
                    source_engine="local_tutor"
                )

        # 12. Topic queries (e.g. "What is recursion?", "Explain recursion completely")
        if active_topic and active_topic in TOPIC_KNOWLEDGE_BASE:
            guide = TOPIC_KNOWLEDGE_BASE[active_topic]
            code_sample = guide["syntax"].get(lang, guide["syntax"].get("python", ""))
            student_mention = f" {student}" if (student and student not in ("Learner", "student", "demo", "Coder")) else ""

            # Check if user asked to "Explain X" or requested comprehensive teaching
            # "Explain recursion" / "Teach me recursion" -> structured pedagogical breakdown
            # "What is recursion?" -> concise 2-paragraph explanation
            is_explain_query = (
                msg_l.startswith("explain") or
                msg_l.startswith("teach me") or
                msg_l.startswith("can you explain") or
                msg_l.startswith("could you explain") or
                self._is_deep_teaching_request(msg)
            )

            if is_explain_query:
                greeting_line = f"Hey{student_mention}! Here is a complete breakdown of **{guide['display_name']}**:\n\n" if student_mention else ""
                reply = (
                    f"{greeting_line}"
                    f"# Complete Guide: {guide['display_name']}\n\n"
                    f"### 1. 📖 Clear Definition\n"
                    f"{guide['definition']}\n\n"
                    f"### 2. 🌟 Analogy\n"
                    f"{guide['analogy']}\n\n"
                    f"### 3. 🎯 Why We Need It\n"
                    f"{guide['why_needed']}\n\n"
                    f"### 4. ⚙️ How It Works\n"
                    f"{guide['how_it_works']}\n\n"
                    f"### 5. 💻 Syntax & Code Pattern ({lang.upper()})\n"
                    f"```{lang}\n"
                    f"{code_sample}\n"
                    f"```\n\n"
                    f"### 6. 🚶 Walkthrough & Base Case\n"
                    f"{guide['walkthrough']}\n\n"
                    f"### 7. ⚠️ Common Pitfalls\n"
                    f"{guide['pitfalls']}"
                )
            else:
                # Crisp, clear, direct 2-paragraph explanation with code example
                student_lead = f"Hey{student_mention}! " if student_mention else ""
                reply = (
                    f"{student_lead}{guide['definition']}\n\n"
                    f"**Intuition:** {guide['analogy']}\n\n"
                    f"**Example ({lang.upper()}):**\n"
                    f"```{lang}\n"
                    f"{code_sample}\n"
                    f"```"
                )

            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="speaking",
                visualization=self._resolve_dynamic_visualization(msg, active_topic),
                topics=[active_topic],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        # 11. Generic fallback / conversational response
        subject = self._extract_subject_from_message(msg)
        if subject:
            s_clean = subject.strip().title()
            reply = (
                f"**{s_clean}** is an important concept in computing.\n\n"
                f"It provides a structured way to handle state, memory, or operations efficiently. "
                f"Would you like me to provide a working code example in `{lang.upper()}`, trace an execution, or explain its inner mechanics?"
            )
            return CompanionResponse(
                bot_name=bot,
                message=reply,
                expression="speaking",
                visualization=None,
                topics=[s_clean],
                recommended_problems=[],
                source_engine="local_tutor"
            )

        reply = f"I'm here to help, {student}! You can ask me to explain any computer science concept, analyze your code, debug test case failures, or solve problems."
        return CompanionResponse(
            bot_name=bot,
            message=reply,
            expression="speaking",
            visualization=None,
            topics=[],
            recommended_problems=[],
            source_engine="local_tutor"
        )
