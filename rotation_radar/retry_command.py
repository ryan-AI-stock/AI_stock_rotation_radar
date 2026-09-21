"""Bounded retries of readiness failures, never silent success or infinite loops."""
import argparse
import subprocess
import time


def run(command, attempts=3, delay=30, execute=subprocess.call, sleep=time.sleep):
    if not 1 <= attempts <= 5 or not 0 <= delay <= 300:
        raise ValueError('Invalid bounded retry settings')
    for attempt in range(1, attempts + 1):
        code = execute(command)
        if code != 75 or attempt == attempts:
            return code
        print(f'Data acquisition not ready: retry {attempt + 1}/{attempts} in {delay}s', flush=True)
        sleep(delay)
    raise AssertionError('unreachable')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--delay', type=int, default=30)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('command required')
    raise SystemExit(run(command, args.attempts, args.delay))


if __name__ == '__main__':
    main()
