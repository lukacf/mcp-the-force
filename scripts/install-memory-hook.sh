#!/bin/bash
# Install git post-commit hook for project memory

HOOK_PATH=".git/hooks/post-commit"

# Create the hook
cat > "$HOOK_PATH" << 'EOF'
#!/bin/sh
# Project memory post-commit hook

# Run in background to not block git
(
    # Ensure we're in the git root
    cd "$(git rev-parse --show-toplevel)"
    
    # Run the memory capture
    python -m mcp_second_brain.memory.commit 2>/dev/null
) &
EOF

# Make it executable
chmod +x "$HOOK_PATH"

echo "Git post-commit hook installed at $HOOK_PATH"
echo "Project memory will now capture commits automatically."