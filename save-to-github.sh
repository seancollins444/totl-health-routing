#!/bin/bash
# Quick save script for pushing changes to GitHub

cd "$(dirname "$0")"

echo "📝 Staging all changes..."
git add .

echo "💬 Enter commit message (or press Enter for default):"
read commit_msg

if [ -z "$commit_msg" ]; then
    commit_msg="Update: $(date '+%Y-%m-%d %H:%M')"
fi

echo "💾 Committing changes..."
git commit -m "$commit_msg"

echo "🚀 Pushing to GitHub..."
git push

echo "✅ Done! Your code is saved to GitHub."
