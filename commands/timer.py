"""Example Python command: timers and reminders with a desktop notification."""
import subprocess
import threading

from blok.plugins import command
from blok.router import number


def _notify(title, body):
    subprocess.run(['notify-send', '--app-name=BLoK', '--urgency=critical', title, body])


@command("Set a timer", phrases=["set a timer for {amount} [minutes]", "timer for {amount} [minutes]",
                                 "remind me in {amount} [minutes] to {task}", "remind me to {task} in {amount} [minutes]"])
def timer(amount, task=None):
    minutes = number(amount)
    if not minutes or minutes > 24 * 60:
        raise RuntimeError('Say a number of minutes, like "set a timer for 5 minutes".')
    seconds_unit = 'second' in amount.lower()
    delay = minutes if seconds_unit else minutes * 60
    what = task or 'Timer done'
    threading.Timer(delay, _notify, args=('BLoK', what)).start()
    unit = 'second' if seconds_unit else 'minute'
    return f"Okay, {what.lower() if task else 'timer'} in {minutes} {unit}{'s' if minutes != 1 else ''}."
