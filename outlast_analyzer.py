import os
import time
import threading
import psutil
import re
import requests
import sys
import winreg
from pathlib import Path
from datetime import datetime
from typing import Optional

__version__ = "1.2.0"

class OutlastTrialsMonitor:
    def __init__(self, silent_mode=False):
        self.is_running = False
        self.silent_mode = silent_mode
        self.user_profile_id = None
        self.processed_players = set()
        self.last_log_position = {}
        self.current_log_file = None
        self.logs_path = Path(os.path.expanduser("~")) / "AppData" / "Local" / "OPP" / "Saved" / "Logs"
        self.api_url = "https://outlasttrialsstats.com/api/profile/contribute"
        self.autostart_key = "OutlastTrialsMonitor"
        self.log_file_path = Path(os.path.expanduser("~")) / "AppData" / "Local" / "OutlastTrialsMonitor.log"

        # Regex patterns
        self.auth_pattern = re.compile(
            r"Client authentication succeeded\. Profile ID: ([0-9a-f-]{36})\. Session ID: ([0-9a-f-]{36})")
        self.player_pattern = re.compile(
            r"RB:\s+\[([^\]]+)\] Player Init Replicated\. Player Id = [^\[]*\[([^\]]*)\] \[([0-9a-f-]{36})\],\s+Player Slot = (\d+), IsLocallyControlled = (Yes|No)")

    def log_message(self, message: str):
        """Logging with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"

        if not self.silent_mode:
            print(log_entry)
        else:
            try:
                with open(self.log_file_path, 'a', encoding='utf-8') as f:
                    f.write(log_entry + "\n")
            except:
                pass

    def setup_autostart(self):
        """Setup autostart"""
        try:
            script_path = Path(sys.argv[0]).resolve()
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                python_exe = sys.executable.replace("python.exe", "pythonw.exe")
                if not os.path.exists(python_exe):
                    python_exe = sys.executable

                command = f'"{python_exe}" "{script_path}" --silent'
                winreg.SetValueEx(key, self.autostart_key, 0, winreg.REG_SZ, command)

            if not self.silent_mode:
                self.log_message("✅ Autostart enabled - script will start automatically with Windows")
            return True
        except Exception as e:
            if not self.silent_mode:
                self.log_message(f"❌ Error setting up autostart: {e}")
            return False

    def remove_autostart(self):
        """Remove autostart registry entry"""
        try:
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self.autostart_key)
            print("✅ Autostart successfully removed")
            return True
        except FileNotFoundError:
            print("ℹ️ Autostart was not configured")
            return False
        except Exception as e:
            print(f"❌ Error removing autostart: {e}")
            return False

    def get_autostart_path(self) -> Optional[str]:
        """Return the exe path stored in the autostart registry entry"""
        try:
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, self.autostart_key)
                # Command is: "exe" "script" --silent  OR  "exe" --silent
                # Extract the last quoted token that ends in .exe or .py
                import shlex
                try:
                    parts = shlex.split(value)
                    for part in parts:
                        if part.lower().endswith(('.exe', '.py')):
                            return part
                except Exception:
                    pass
                return value
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def print_status(self):
        """Print autostart and process status"""
        print("=" * 60)
        print("    OutlastTrials Monitor - Status")
        print("=" * 60)

        # Check if monitor process is running
        monitor_pid = None
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] == current_pid:
                    continue
                name = proc.info.get('name') or ''
                cmdline = proc.info.get('cmdline') or []
                if 'TOTStatsMonitor' in name:
                    monitor_pid = proc.info['pid']
                    break
                if any('outlast_analyzer' in str(arg) for arg in cmdline):
                    monitor_pid = proc.info['pid']
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if monitor_pid:
            print(f"✅ Monitor is RUNNING (PID: {monitor_pid})")
            print(f"   To stop: end 'TOTStatsMonitor.exe' in Task Manager")
        else:
            print("❌ Monitor is NOT running")

        print()

        # Check autostart
        stored_path = self.get_autostart_path()
        if stored_path:
            if os.path.exists(stored_path):
                print(f"✅ Autostart: configured (path valid)")
                print(f"   Path: {stored_path}")
            else:
                print(f"⚠️  Autostart: configured but path INVALID")
                print(f"   Configured: {stored_path}")
                print(f"   The file was moved or deleted!")
                print(f"   → Run the program again to fix the path automatically")
                print(f"   → Or run with --uninstall to remove the broken entry")
        else:
            print("❌ Autostart: not configured")

        print()
        print("Commands:  --uninstall   remove autostart")
        print("           --status      show this info")
        print("=" * 60)

    def is_outlast_running(self) -> bool:
        """Check if OutlastTrials is running"""
        for process in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                process_info = process.info
                if process_info['name'] and 'TOTClient' in process_info['name']:
                    return True
                if process_info['exe'] and 'TOTClient' in process_info['exe']:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def get_newest_log_file(self) -> Optional[Path]:
        """Find newest log file"""
        if not self.logs_path.exists():
            return None

        log_files = list(self.logs_path.glob("*.log"))
        if not log_files:
            return None

        newest_file = max(log_files, key=lambda x: x.stat().st_mtime)
        return newest_file

    def parse_user_profile_id(self, log_content: str) -> Optional[str]:
        """Parse user profile ID from logs"""
        match = self.auth_pattern.search(log_content)
        if match:
            return match.group(1)
        return None

    def parse_players_from_logs(self, log_content: str) -> list:
        """Parse players from logs"""
        players = []
        matches = self.player_pattern.findall(log_content)

        for match in matches:
            player_name, player_id_short, profile_uuid, slot, is_local = match
            players.append({
                'name': player_name,
                'id_short': player_id_short,
                'profile_uuid': profile_uuid,
                'slot': int(slot),
                'is_local': is_local == 'Yes'
            })

        players.sort(key=lambda x: x['slot'])
        return players

    def send_contribution_request(self, contributor_id: str, profile_id: str):
        """Send API request"""
        try:
            url = f"{self.api_url}?contributor={contributor_id}&profile={profile_id}"
            response = requests.put(url, timeout=10)

            if response.status_code == 200:
                self.log_message(f"✅ Player data sent successfully: {profile_id[:8]}...")
            elif response.status_code == 208:
                self.log_message(f"ℹ️ Player already known: {profile_id[:8]}...")
            else:
                self.log_message(f"⚠️ API error (Status {response.status_code})")

        except requests.exceptions.RequestException as e:
            self.log_message(f"❌ Network error: {e}")

    def process_log_file(self, log_file: Path):
        """Process log file"""
        try:
            file_key = str(log_file)
            last_pos = self.last_log_position.get(file_key, 0)

            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(last_pos)
                new_content = f.read()

                if new_content:
                    self.last_log_position[file_key] = f.tell()

                    if not self.user_profile_id:
                        self.user_profile_id = self.parse_user_profile_id(new_content)
                        if self.user_profile_id:
                            self.log_message(f"🆔 Player ID found: {self.user_profile_id[:8]}...")

                    if self.user_profile_id:
                        players = self.parse_players_from_logs(new_content)

                        for player in players:
                            if not player['is_local'] and player['profile_uuid'] not in self.processed_players:
                                self.processed_players.add(player['profile_uuid'])
                                self.log_message(f"🎮 New player: {player['name']} (Slot {player['slot']})")
                                self.send_contribution_request(self.user_profile_id, player['profile_uuid'])

        except Exception as e:
            self.log_message(f"Error processing log file: {e}")

    def monitor_logs(self):
        """Monitor logs"""
        while self.is_running:
            try:
                newest_log_file = self.get_newest_log_file()

                if newest_log_file:
                    if self.current_log_file != newest_log_file:
                        if self.current_log_file:
                            self.log_message(f"📄 Switching to newer log file: {newest_log_file.name}")
                        else:
                            self.log_message(f"📄 Monitoring log file: {newest_log_file.name}")

                        self.current_log_file = newest_log_file
                        file_key = str(newest_log_file)
                        if file_key not in self.last_log_position:
                            self.last_log_position[file_key] = 0

                    self.process_log_file(self.current_log_file)
                else:
                    if not self.silent_mode:
                        self.log_message("⚠️ No log files found - play OutlastTrials to generate logs")

                time.sleep(15)

            except Exception as e:
                self.log_message(f"Error monitoring logs: {e}")
                time.sleep(15)

    def monitor_game_process(self):
        """Monitor game process"""
        while True:
            try:
                if self.is_outlast_running() and not self.is_running:
                    self.log_message("🎮 OutlastTrials detected! Starting data collection...")
                    self.start_monitoring()

                elif not self.is_outlast_running() and self.is_running:
                    self.log_message("🛑 OutlastTrials closed. Stopping data collection...")
                    self.stop_monitoring()

                time.sleep(5)

            except Exception as e:
                self.log_message(f"Error monitoring game process: {e}")
                time.sleep(10)

    def start_monitoring(self):
        """Start monitoring"""
        if self.is_running:
            return

        self.is_running = True
        self.user_profile_id = None
        self.processed_players.clear()
        self.last_log_position.clear()
        self.current_log_file = None

        self.log_thread = threading.Thread(target=self.monitor_logs, daemon=True)
        self.log_thread.start()

    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_running = False

    def run(self):
        """Main program"""
        self.setup_autostart()
        self.log_message("🚀 OutlastTrials Monitor started")

        try:
            self.monitor_game_process()
        except KeyboardInterrupt:
            self.log_message("🛑 Monitor is shutting down...")
            self.stop_monitoring()


def main():
    """Main function - simple and user-friendly"""

    # Silent mode for autostart
    if len(sys.argv) > 1 and "--silent" in sys.argv:
        monitor = OutlastTrialsMonitor(silent_mode=True)
        monitor.run()
        return

    # Uninstall
    if len(sys.argv) > 1 and "--uninstall" in sys.argv:
        monitor = OutlastTrialsMonitor()
        monitor.remove_autostart()
        print()
        print("To fully uninstall, delete the TOTStatsMonitor.exe file.")
        print("If the monitor is still running, end it in Task Manager.")
        return

    # Status
    if len(sys.argv) > 1 and "--status" in sys.argv:
        monitor = OutlastTrialsMonitor()
        monitor.print_status()
        return

    # Show help
    if len(sys.argv) > 1 and ("--help" in sys.argv or "-h" in sys.argv):
        print("OutlastTrials Stats Contributor")
        print("")
        print("Just start the program - everything else happens automatically!")
        print("")
        print("What happens:")
        print("• Autostart is set up")
        print("• OutlastTrials is monitored")
        print("• Player data is sent")
        print("")
        print("Flags:")
        print("  --status     Show whether monitor is running and autostart is configured")
        print("  --uninstall  Remove autostart registry entry")
        print("")
        print("That's it! No further configuration needed.")
        return

    monitor = OutlastTrialsMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
