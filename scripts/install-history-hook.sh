#!/bin/bash
# Install optimized git post-commit hook for project history

HOOK_PATH=".git/hooks/post-commit"
SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check if optimized hook script exists
if [ -f "$SCRIPT_DIR/optimized-post-commit-hook.sh" ]; then
    echo "Installing optimized post-commit hook..."
    cp "$SCRIPT_DIR/optimized-post-commit-hook.sh" "$HOOK_PATH"
    chmod +x "$HOOK_PATH"
    echo "✅ Optimized git post-commit hook installed at $HOOK_PATH"
    echo "🚀 Expected performance: 50-150ms per execution"
else
    echo "⚠️  Optimized hook script not found, installing basic version..."
    # Create the basic hook as fallback
    cat > "$HOOK_PATH" << 'EOF'
#!/bin/sh
# Project history post-commit hook (basic version)

# Run in background to not block git
(
    # Ensure we're in the git root
    cd "$(git rev-parse --show-toplevel)"
    
    # Try optimized path first, fallback to standard
    if [ -f "mcp_the_force/history/fast_commit.py" ]; then
        python3 -c "import sys; sys.path.insert(0, '.'); from mcp_the_force.history.fast_commit import record_commit_fast; record_commit_fast()" 2>/dev/null
    else
        python3 -m mcp_the_force.history.commit 2>/dev/null
    fi
) &
EOF
    chmod +x "$HOOK_PATH"
    echo "✅ Basic git post-commit hook installed at $HOOK_PATH"
fi

echo ""
echo "Project history will now capture commits automatically."
echo ""
echo "💡 Performance Tips:"
echo "   • Run 'scripts/benchmark-hook-performance.py' to test performance"
echo "   • Expected execution time should be <100ms"
echo "   • Monitor with: time git commit -m 'test'"