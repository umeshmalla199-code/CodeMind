# Locate the unclosed brace / paren / bracket in scratch/script_1.js
# We can use binary search or line-by-line paren tracking, ignoring string literals, comments, template literals, and regexes.

def find_unclosed():
    with open("scratch/script_1.js", "r", encoding="utf-8") as f:
        code = f.read()

    lines = code.split("\n")
    print(f"Total lines: {len(lines)}")

    # Let's do a bisection test: add closing braces/parens to see where node --check gives a different error or succeeds.
    # But even better: let's track tokens accurately.
    i = 0
    n = len(code)
    stack = [] # (char, line_num, col_num)
    
    line = 1
    col = 1
    
    in_single_comment = False
    in_multi_comment = False
    in_single_quote = False
    in_double_quote = False
    in_template = False
    template_stack = [] # tracks { inside ${} in template strings
    
    while i < n:
        c = code[i]
        
        # update line/col
        if c == '\n':
            line += 1
            col = 0
            if in_single_comment:
                in_single_comment = False
            i += 1
            col += 1
            continue
            
        if in_single_comment:
            i += 1
            col += 1
            continue
            
        if in_multi_comment:
            if c == '*' and i + 1 < n and code[i+1] == '/':
                in_multi_comment = False
                i += 2
                col += 2
                continue
            i += 1
            col += 1
            continue
            
        if in_single_quote:
            if c == '\\':
                i += 2
                col += 2
                continue
            if c == "'":
                in_single_quote = False
            i += 1
            col += 1
            continue
            
        if in_double_quote:
            if c == '\\':
                i += 2
                col += 2
                continue
            if c == '"':
                in_double_quote = False
            i += 1
            col += 1
            continue
            
        if in_template:
            if c == '\\':
                i += 2
                col += 2
                continue
            if c == '$' and i + 1 < n and code[i+1] == '{':
                template_stack.append(len(stack))
                i += 2
                col += 2
                in_template = False
                stack.append(('${', line, col))
                continue
            if c == '`':
                in_template = False
            i += 1
            col += 1
            continue
            
        # Outside strings / comments
        if c == '/' and i + 1 < n:
            if code[i+1] == '/':
                in_single_comment = True
                i += 2
                col += 2
                continue
            elif code[i+1] == '*':
                in_multi_comment = True
                i += 2
                col += 2
                continue
                
        if c == "'":
            in_single_quote = True
            i += 1
            col += 1
            continue
            
        if c == '"':
            in_double_quote = True
            i += 1
            col += 1
            continue
            
        if c == '`':
            in_template = True
            i += 1
            col += 1
            continue
            
        if c in '({[':
            stack.append((c, line, col))
        elif c in ')}]':
            matching = {'(': ')', '{': '}', '[': ']' }
            if not stack:
                print(f"Error: extra closing {c} at line {line}:{col}")
            else:
                top, top_line, top_col = stack.pop()
                if top == '${' and c == '}':
                    in_template = True
                elif matching.get(top) != c:
                    print(f"Mismatch: expected {matching.get(top)} for {top} from line {top_line}:{top_col}, but found {c} at line {line}:{col}")
        i += 1
        col += 1

    print(f"Finished parsing. Stack length: {len(stack)}")
    for item in stack[-10:]:
        print(f"Unclosed {item[0]} at line {item[1]}:{item[2]}")

if __name__ == '__main__':
    find_unclosed()
