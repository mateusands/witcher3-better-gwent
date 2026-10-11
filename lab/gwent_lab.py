#!/usr/bin/env python3
"""Gwent AI Lab: local panel (http://127.0.0.1:8765) and worker manager.

    python3 lab/gwent_lab.py            start the panel and open it in the browser
    python3 lab/gwent_lab.py --no-open  (server/headless; reach it through an SSH tunnel)

The panel only listens on 127.0.0.1. On the PC the lab always starts paused (press Resume);
with the setting autoresume=true (server) it continues on its own after a reboot.
Workers run at low priority, their number is adjustable live, and they stop while a listed
game process (default witcher3.exe) runs or when the data folder exceeds its disk cap.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

HERE = Path(__file__).resolve().parent


class Manager:
    def __init__(self, root):
        self.root = root
        self.db = core.init(root)
        self.workers = {}            # pid -> Popen
        self.commands = {}           # pid -> command it was started with
        self.auto_pause = None       # None, 'game' or 'disk'
        self.lab_bytes = 0
        self.lock = threading.Lock()
        self.stopping = False

    def settings(self):
        return {k: core.get(self.db, k) for k in core.DEFAULT_SETTINGS}

    def desired(self):
        if core.get(self.db, 'paused') or self.auto_pause:
            return 0
        return max(0, min(os.cpu_count() or 1, int(core.get(self.db, 'workers'))))

    def worker_command(self):
        python = core.get(self.db, 'worker_python') or sys.executable
        if not shutil.which(python) and not os.path.isfile(python):
            python = sys.executable        # configured interpreter missing: fall back
        return [python, str(HERE / 'core.py'), '--worker', str(self.root)]

    def stop_worker(self, pid):
        proc = self.workers.pop(pid)
        self.commands.pop(pid, None)
        if proc.poll() is None:
            os.kill(pid, signal.SIGKILL)   # same as a power cut; the task is simply redone
        proc.wait()
        self.db.execute("UPDATE tasks SET status='pending', worker=NULL, started=NULL "
                        "WHERE status='running' AND worker=?", (pid,))

    def reconcile(self):
        with self.lock:
            command = self.worker_command()
            for pid, proc in list(self.workers.items()):
                # Dead workers, and workers started with another interpreter setting, are replaced.
                if proc.poll() is not None or self.commands.get(pid) != command:
                    self.stop_worker(pid)
            want = 0 if self.stopping else self.desired()
            while len(self.workers) > want:
                self.stop_worker(next(iter(self.workers)))
            while len(self.workers) < want:
                proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.workers[proc.pid] = proc
                self.commands[proc.pid] = command

    def game_running(self):
        names = [n.lower() for n in core.get(self.db, 'pause_on_processes') or []]
        if not names:
            return False
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                argv0 = (proc.info['cmdline'] or [''])[0]
            except (psutil.Error, TypeError, IndexError):
                continue
            # Executable names only (Proton/Wine argv[0] may be a Windows path); a shell
            # command line that merely mentions the name must not pause the lab.
            candidates = {(proc.info['name'] or '').lower(), argv0.replace('\\', '/').rsplit('/', 1)[-1].lower()}
            if any(n in candidates for n in names):
                return True
        return False

    def loop(self):
        last_disk = 0
        while not self.stopping:
            now = time.time()
            if now - last_disk > 30:
                self.lab_bytes = core.dir_size(self.root)
                last_disk = now
            cap = float(core.get(self.db, 'disk_cap_gb')) * 1024 ** 3
            self.auto_pause = 'disk' if self.lab_bytes > cap else 'game' if self.game_running() else None
            if not self.auto_pause and not core.get(self.db, 'paused'):
                core.refill(self.db)
                core.tune_step(self.db)
            self.reconcile()
            time.sleep(3)

    def shutdown(self):
        self.stopping = True
        self.reconcile()


def gpu_stats():
    for card in sorted(Path('/sys/class/drm').glob('card[0-9]')):
        dev = card / 'device'
        try:
            busy = int((dev / 'gpu_busy_percent').read_text())
            used = int((dev / 'mem_info_vram_used').read_text())
            total = int((dev / 'mem_info_vram_total').read_text())
            return dict(busy=busy, vramUsed=used, vramTotal=total)
        except (OSError, ValueError):
            continue
    return None


def status(manager):
    db = core.connect(manager.root)
    jobs = [core.job_summary(db, j) for j in db.execute(
        'SELECT id,name,kind,params,created,status FROM jobs ORDER BY id DESC')]
    active = len(manager.workers)
    for job in jobs:
        remaining = job['pending'] + job['running']
        job['etaSeconds'] = (remaining * job['avgTaskSeconds'] / active) if job['avgTaskSeconds'] and active else None
    worker_cpu = worker_ram = 0.0
    for pid in list(manager.workers):
        try:
            p = psutil.Process(pid)
            worker_cpu += p.cpu_percent(None)
            worker_ram += p.memory_info().rss
        except psutil.Error:
            pass
    vm = psutil.virtual_memory(); disk = shutil.disk_usage(manager.root)
    settings = manager.settings()
    db.close()
    return dict(
        state='paused' if settings['paused'] else ('auto-paused: ' + manager.auto_pause) if manager.auto_pause else 'running',
        settings=settings, activeWorkers=active, cpuCount=os.cpu_count(),
        workerEngine=os.path.basename(manager.worker_command()[0]),
        system=dict(cpu=psutil.cpu_percent(None), workerCpu=worker_cpu, ramUsed=vm.used, ramTotal=vm.total,
                    workerRam=worker_ram, gpu=gpu_stats(), labBytes=manager.lab_bytes,
                    diskFree=disk.free, diskTotal=disk.total, dataRoot=str(manager.root)),
        jobs=jobs)


def make_handler(manager):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, kind='application/json'):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/':
                return self.send(200, (HERE / 'panel.html').read_bytes(), 'text/html; charset=utf-8')
            if self.path == '/api/status':
                return self.send(200, status(manager))
            self.send(404, {'error': 'not found'})

        def do_POST(self):
            length = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(length) or b'{}')
            db = core.connect(manager.root)
            try:
                if self.path == '/api/resume':
                    core.set_(db, 'paused', False)
                elif self.path == '/api/pause':
                    core.set_(db, 'paused', True)
                elif self.path == '/api/settings':
                    for key in ('workers', 'disk_cap_gb', 'autoresume', 'pause_on_processes', 'worker_python'):
                        if key in body:
                            core.set_(db, key, body[key])
                elif self.path == '/api/job':
                    kind = body.get('kind', 'benchmark')
                    params = dict(source=body['source'], policy=body.get('policy', 'response-v8'),
                                  profile=body.get('profile', 'hard'), seeds=[int(s) for s in body['seeds']],
                                  continuous=bool(body.get('continuous')))
                    if body.get('player_filter'):
                        params['player_filter'] = body['player_filter']
                    if body.get('npc_decks'):
                        params['npc_decks'] = body['npc_decks']
                    if body.get('weights'):
                        params['weights'] = {k: float(v) for k, v in body['weights'].items()}
                    if body['source'] in ('pool', 'player'):
                        params['pairs'] = int(body['pairs']) if body.get('pairs') else None
                    else:
                        params['records'] = body['records']
                    if kind == 'tune':
                        params = dict(profile=body.get('profile', 'hard'), policy='response-v8',
                                      **{k: body[k] for k in core.TUNE_DEFAULTS if k in body})
                    core.create_job(db, body.get('name') or kind, kind, params)
                elif self.path == '/api/quit':
                    core.set_(db, 'paused', True)
                    threading.Timer(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
                elif self.path == '/api/job/status':
                    db.execute('UPDATE jobs SET status=? WHERE id=?', (body['status'], int(body['id'])))
                else:
                    return self.send(404, {'error': 'not found'})
            except (KeyError, ValueError, core.LabError) as exc:
                return self.send(400, {'error': str(exc)})
            finally:
                db.close()
            manager.reconcile()
            self.send(200, {'ok': True})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', help='data root (default /mnt/hdd/GwentAILab)')
    parser.add_argument('--port', type=int, default=int(os.environ.get('GWENT_LAB_PORT', 8765)))
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    url = 'http://127.0.0.1:%d/' % args.port
    try:
        import urllib.request
        urllib.request.urlopen(url + 'api/status', timeout=2)
        # Already running (e.g. the desktop shortcut was clicked again): just show the panel.
        if not args.no_open:
            webbrowser.open(url)
        print('Gwent AI Lab already running: %s' % url)
        return
    except OSError:
        pass
    root = core.data_root(args.data)
    manager = Manager(root)
    threading.Thread(target=manager.loop, daemon=True).start()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(manager))
    print('Gwent AI Lab: %s (data: %s)' % (url, root), flush=True)
    if not args.no_open:
        threading.Timer(1.0, webbrowser.open, (url,)).start()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
