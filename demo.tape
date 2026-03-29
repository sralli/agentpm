Output demo.gif

Set Theme "Catppuccin Mocha"
Set FontSize 15
Set Width 1100
Set Height 650
Set Padding 20
Set TypingSpeed 35ms
Set Shell zsh

# Init
Type "agendum init"
Enter
Sleep 1.5s

# Create project
Type "agendum project create webapp -d 'E-commerce platform'"
Enter
Sleep 1.2s

# Create tasks with dependencies
Type "agendum task create webapp 'Set up database schema' -p high"
Enter
Sleep 1s

Type "agendum task create webapp 'Build user auth' -p high --depends-on task-001"
Enter
Sleep 1s

Type "agendum task create webapp 'Add product API' -p medium --depends-on task-001"
Enter
Sleep 1s

Type "agendum task create webapp 'Checkout flow' --depends-on task-002,task-003"
Enter
Sleep 1.2s

# Show task list
Type "agendum task list webapp"
Enter
Sleep 3s

# Board overview
Type "agendum status"
Enter
Sleep 3s

# What to work on next
Type "agendum next webapp"
Enter
Sleep 3s

# Closing message
Type "# 32 MCP tools — works with Claude Code, Cursor, Windsurf, Cline"
Enter
Sleep 2.5s
