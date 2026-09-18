# launcher.py
# language: Python, target: Windows 10/11, Python 3.10+
# *локальный оркестратор: держит bot.py + Roblox. На BotHost не используется.*

import os
import sys
import time
import socket
import subprocess
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

ROBLOX_EXE     = os.getenv("ROBLOX_EXE", "RobloxPlayerBeta.exe")
EXECUTOR_EXE   = os.getenv("EXECUTOR_EXE", "")
EXECUTOR_ARGS  = os.getenv("EXECUTOR_ARGS", "--inject")
AUTOEXEC_DIR   = os.getenv("AUTOEXEC_DIR", "")
GAME_URL       = os.getenv("GAME_URL", "roblox://placeId=PLACE_ID_HERE")
WEBHOOK_PORT   = int(os.getenv("PORT") or os.getenv("WEBHOOK_PORT", 8080))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 30))
LUA_SCRIPT     = Path(__file__).parent / "egg_watcher.lua"
BOT_SCRIPT     = Path(__file__).parent / "bot.py"

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s — %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("launcher")

def is_process_running(name: str) -> bool:
    try:
        out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                                      stderr=subprocess.DEVNULL, text=True,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        return name.lower() in out.lower()
    except Exception:
        return False

def is_port_alive(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.5)
        return s.connect_ex(("127.0.0.1", port)) == 0

def launch_roblox():
    log.info("Roblox не найден — запускаю")
    try:
        os.startfile(GAME_URL)
    except Exception as e:
        log.error("не удалось запустить Roblox: %s", e)

def deploy_autoexec():
    if not AUTOEXEC_DIR:
        return
    target_dir = Path(AUTOEXEC_DIR)
    if not target_dir.exists():
        log.warning("autoexec папка не найдена: %s", target_dir)
        return
    (target_dir / "egg_watcher.lua").write_text(LUA_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    log.info("Lua развёрнут в autoexec")

def push_lua_via_executor():
    if not EXECUTOR_EXE or not Path(EXECUTOR_EXE).exists():
        return False
    try:
        subprocess.Popen([EXECUTOR_EXE, "--script", str(LUA_SCRIPT)],
                         creationflags=subprocess.CREATE_NO_WINDOW)
        log.info("Lua отправлен через CLI")
        return True
    except Exception:
        return False

class BotManager:
    def __init__(self): self.proc = None
    def start(self):
        if self.proc and self.proc.poll() is None: return
        log.info("поднимаю bot.py")
        self.proc = subprocess.Popen([sys.executable, str(BOT_SCRIPT)],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
    def ensure(self):
        if self.proc is None or self.proc.poll() is not None:
            log.warning("бот упал — перезапускаю"); self.start()
        elif not is_port_alive(WEBHOOK_PORT):
            log.warning("порт %s не слушается — перезапускаю", WEBHOOK_PORT)
            self.kill(); self.start()
    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired: self.proc.kill()

def main():
    log.info("=== launcher запущен ===")
    bot = BotManager(); bot.start()
    for _ in range(30):
        if is_port_alive(WEBHOOK_PORT):
            log.info("бот слушает порт %s", WEBHOOK_PORT); break
        time.sleep(1)
    deploy_autoexec()
    roblox_was_running = False
    injected = False
    while True:
        try:
            if not is_process_running(ROBLOX_EXE):
                if roblox_was_running: log.warning("Roblox упал — перезапускаю"); injected = False
                launch_roblox(); roblox_was_running = True; time.sleep(15); continue
            if not injected and push_lua_via_executor():
                injected = True; log.info("инжект выполнен")
            bot.ensure()
        except KeyboardInterrupt:
            log.info("стоп"); bot.kill(); break
        except Exception as e:
            log.exception("цикл упал: %s", e)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
