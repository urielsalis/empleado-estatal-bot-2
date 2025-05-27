#!/bin/bash

# Configuration
SCREEN_NAME="empleado-estatal-bot"
LOG_FILE="bot.log"
MAX_RESTARTS=5
RESTART_DELAY=10

# Function to check if screen is installed
check_screen() {
    if ! command -v screen &> /dev/null; then
        echo "Error: screen is not installed. Please install it first."
        echo "On macOS: brew install screen"
        echo "On Ubuntu/Debian: sudo apt-get install screen"
        exit 1
    fi
}

# Function to start the service
start_service() {
    local restart_count=0
    
    while [ $restart_count -lt $MAX_RESTARTS ]; do
        echo "$(date): Starting service (attempt $((restart_count + 1))/$MAX_RESTARTS)" >> "$LOG_FILE"
        
        # Run the service
        uv run main.py 2>&1 | tee -a "$LOG_FILE"
        
        # Check if the service exited with an error
        if [ $? -ne 0 ]; then
            restart_count=$((restart_count + 1))
            echo "$(date): Service crashed. Restarting in $RESTART_DELAY seconds..." >> "$LOG_FILE"
            sleep $RESTART_DELAY
        else
            # If the service exited normally, break the loop
            echo "$(date): Service exited normally" >> "$LOG_FILE"
            break
        fi
    done
    
    if [ $restart_count -eq $MAX_RESTARTS ]; then
        echo "$(date): Maximum restart attempts reached. Service failed to start properly." >> "$LOG_FILE"
        exit 1
    fi
}

# Main execution
check_screen

# Check if screen session already exists
if ! screen -list | grep -q "$SCREEN_NAME"; then
    echo "Creating new screen session: $SCREEN_NAME"
    screen -dmS "$SCREEN_NAME" bash -c "$(pwd)/run.sh"
    echo "Service started in screen session. Use 'screen -r $SCREEN_NAME' to attach to the session."
else
    echo "Screen session already exists. Starting service..."
    start_service
fi 