#!/usr/bin/env python3
"""Build a fresh production R10 ELF and require the selected host/QEMU baseline."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_output(path):
    """Never reuse build objects, logs or a report from a previous invocation."""
    if path is None:
        parent = ROOT/'build'
        parent.mkdir(exist_ok=True)
        return Path(tempfile.mkdtemp(prefix='baseline-', dir=parent))
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def stop_group(process):
    # QEMU tests start their own sessions. Capture descendants before killing
    # their parent; pidfds avoid signalling a recycled PID during cleanup.
    handles = []
    pending = [process.pid]
    try:
        while pending:
            pid = pending.pop()
            try:
                children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
            except FileNotFoundError:
                continue
            for child in map(int, children):
                try:
                    handles.append(os.pidfd_open(child))
                    pending.append(child)
                except ProcessLookupError:
                    pass
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            for fd in handles:
                try:
                    signal.pidfd_send_signal(fd, sig)
                except ProcessLookupError:
                    pass
            if sig == signal.SIGTERM:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        process.wait()
    finally:
        for fd in handles:
            os.close(fd)


def run_step(name, command, output, env, timeout, required=()):
    """Exit zero alone is insufficient: require the stage's coverage markers too."""
    log = output/(name+'.log')
    started = time.monotonic()
    timed_out = False
    with log.open('xb') as stream:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            stop_group(process)
    text = log.read_text(errors='replace')
    missing = [pattern for pattern in required if not re.search(pattern, text, re.MULTILINE)]
    passed = not timed_out and process.returncode == 0 and not missing
    return {'name': name, 'command': command, 'status': 'passed' if passed else 'failed',
            'returncode': process.returncode, 'timed_out': timed_out,
            'missing_markers': missing, 'seconds': round(time.monotonic()-started, 3),
            'log': log.name, 'log_sha256': sha256(log)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        help='new directory for logs, JSON and fresh build (default: build/baseline-*)')
    parser.add_argument('--system-tools', action='store_true',
                        help='use the cross-compiler and QEMU on PATH, ignoring tools/root')
    parser.add_argument('--timeout', type=int, default=180, help='seconds per stage (default: 180)')
    args = parser.parse_args()
    if sys.flags.optimize:
        parser.error('Python optimization disables test assertions; remove -O/PYTHONOPTIMIZE')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    try:
        output = new_output(args.output_dir)
    except OSError as error:
        parser.error(f'cannot create a fresh output directory: {error}')
    env = dict(os.environ, PYTHONUNBUFFERED='1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    if args.system_tools:
        env['USE_SYSTEM_TOOLS'] = '1'
    build = output/'r10'
    elf = build/'r10_payload.elf'
    python = sys.executable
    stages = [
        ('01-runner-contract', [python, str(ROOT/'scripts/test_baseline_runner.py')],
         (r'^BASELINE RUNNER PASS$',)),
        ('02-tool-versions', ['make', '-s', '-C', str(ROOT/'r8'), 'tool_versions'], ()),
        ('03-build-r10', ['make', '-C', str(ROOT/'r8'), f'BUILD={build}', str(elf)], ()),
        ('04-fdt', [python, str(ROOT/'scripts/test_fdt.py')],
         (r'^FDT MODEL PASS: 43 cases with ASan/UBSan$',)),
        ('05-payload', [python, str(ROOT/'scripts/test_payload.py'), '--elf', str(elf)],
         (r'^R10 ELF extent PASS: BSS and all stacks included$',
          r'^PAYLOAD PASS: 60 cases; C consumer with ASan/UBSan$')),
        ('06-payload-stage', [python, str(ROOT/'scripts/test_payload_stage.py')],
         (r'^PAYLOAD STAGE PASS: 17 cases; exact bytes, guards and no writes on rejection$',)),
        ('07-entry-diag', [python, str(ROOT/'scripts/test_entry_diag.py')],
         (r'^ENTRY DIAG: 6 accepted entries \+ 6 M/C refusals PASS; one CPU, no Samsung hardware claim$',)),
        ('08-payload-loader', [python, str(ROOT/'scripts/test_payload_loader.py')],
         (r'^EL2 MATERIALIZE PASS: exact PT_LOADs, BSS, stacks, FDT and guards$',
          r'^R10 CONTAINER HANDOFF PASS: production main at EL1, raw FDT, [1-9][0-9]* timer IRQs$',
          r'^PAYLOAD LOADER QEMU PASS: 1 production handoff \+ 5 refusal cases, one CPU$')),
    ]
    report = {'schema_version': 1, 'status': 'failed',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'python': sys.version, 'platform': platform.platform(),
              'system_tools': env.get('USE_SYSTEM_TOOLS') == '1',
              'timeout_per_stage': args.timeout, 'output': str(output),
              'required_stages': [name for name, _, _ in stages], 'steps': []}
    print(f'Baseline logs: {output}', flush=True)
    try:
        for name, command, required in stages:
            print(f'RUN {name}', flush=True)
            try:
                result = run_step(name, command, output, env, args.timeout, required)
            except OSError as error:
                result = {'name': name, 'command': command, 'status': 'failed', 'error': str(error)}
            report['steps'].append(result)
            if result['status'] != 'passed':
                print(f'FAIL {name}: {json.dumps(result)}', flush=True)
                log = output/(name+'.log')
                if log.exists():
                    print('\n'.join(log.read_text(errors='replace').splitlines()[-40:]))
                return 1
            print(f'PASS {name}', flush=True)
        report['elf'] = {'path': str(elf), 'sha256': sha256(elf), 'bytes': elf.stat().st_size}
        report['status'] = 'passed'
        print('BASELINE PASS: fresh R10 ELF, host 43/60/17, diagnostic 12, loader 1+5', flush=True)
        return 0
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    sys.exit(main())
