#!/bin/bash
#chmod +x ramcc.sh
#./ramcc.sh
echo "🚀 Starting deep RAM cleanup..."

# 1. Kill Browsers
echo "Closing Browsers..."
pkill -9 -f "opera"
pkill -9 -f "chrome"

# 2. Kill Messaging Apps
echo "Stopping Dropbox and WhatsApp..."
pkill -9 -f "dropbox"
pkill -9 -f "WhatsApp"
pkill -9 -f "whatsapp"  # lowercase# or
killall WhatsApp
killall whatsie
killall -9 whatsie

# 3. Kill Electron/Code Helpers (The heavy items in image_4.png)
echo "Killing VS Code, Atom, and Kiro background services..."
pkill -9 -f "vscode"
pkill -9 -f "atom"
pkill -9 -f "kiro"
pkill -9 -f "NodeService"
killall -9 node

# 4. Kill Development & Workflow Tools
echo "Stopping n8n and Ollama..."
pkill -9 -f "n8n"
#pkill -9 -f "ollama"

# 5. Stop Multipass Daemon
echo "Stopping Multipass..."
sudo systemctl stop snap.multipass.multipassd

# 6. Clear System Cache (Optional but helpful)
echo "Clearing System Buffers/Cache..."
sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches

echo "✅ Done! Check your RAM usage with 'free -h'."
