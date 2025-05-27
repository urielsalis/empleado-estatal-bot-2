import os
import sqlite3
import subprocess
import tempfile
import time
import signal
import pytest
from pathlib import Path

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)

@pytest.fixture
def bot_process(temp_dir):
    # Use the existing config.yml
    real_config_path = Path("config/config.yml")
    assert real_config_path.exists(), f"Config file {real_config_path} not found."
    
    # Patch the DB location by setting the DATA_DIR env var
    env = os.environ.copy()
    env["DATA_DIR"] = str(temp_dir)
    
    # Run the bot as a subprocess in the background
    proc = subprocess.Popen(
        ["uv", "run", "main.py"],
        cwd=Path(__file__).parent.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True  # Run in a new process group
    )
    
    yield proc
    
    # Cleanup - terminate the entire process group
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
    
    stdout, stderr = proc.communicate()
    if stdout:
        print("\nBot stdout:", stdout)
    if stderr:
        print("\nBot stderr:", stderr)

def test_bot_runs_and_writes_to_test_db(temp_dir, bot_process):
    test_db_path = temp_dir / "bot.db"
    
    # Wait for the bot to start and write to the DB
    max_wait = 5  # Maximum wait time in seconds
    start_time = time.time()
    
    while not test_db_path.exists() and time.time() - start_time < max_wait:
        time.sleep(0.1)
        if bot_process.poll() is not None:
            pytest.fail("Bot process terminated unexpectedly")
    
    # Verify database was created
    assert test_db_path.exists(), f"Test DB {test_db_path} was not created within {max_wait} seconds"
    
    # Verify database structure
    conn = sqlite3.connect(test_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "posts" in tables, "'posts' table not found in test DB"
        assert "texts" in tables, "'texts' table not found in test DB"
    finally:
        conn.close() 