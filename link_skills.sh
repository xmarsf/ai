#!/bin/bash

mkdir -p ~/.claude/skills

for dir in "$PWD"/skills/*/; do
  # Check if directory exists to avoid errors if skills folder is empty
  if [ -d "$dir" ]; then
    name=$(basename "$dir")
    ln -sf "$dir" ~/.claude/skills/"$name"
    echo "Symlinked $name to ~/.claude/skills/$name"
  fi
done
