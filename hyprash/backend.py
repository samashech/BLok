"""JSON-lines bridge between Quickshell, Voxtype and local Laya decisions."""
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

from hyprash.commands import StreamPlanner, parse
from hyprash import browser, desktop
from hyprash.decision import LayaDecision
from hyprash.themes import ThemeStore

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("HYPRASH_DATA", ROOT / "data"))

class Backend:
    def __init__(self):
        self.output_lock = threading.Lock()
        self.events = queue.Queue()
        self.generation = 0
        self.listening = False
        self.planner = StreamPlanner()
        self.note = None
        self.notes_target = "hyprash"
        self.camera_target = "hyprash"
        self.external_note_title = None
        self.action_jobs = queue.Queue()
        self.action_worker = None
        self.actions_pending = 0
        self.worker_context = threading.local()
        self.voice = None
        self.decisions = queue.Queue(maxsize=8)
        self.decision_worker = None
        self.pending = 0
        self.themes = ThemeStore(DATA)

    def emit(self, **event):
        generation=getattr(self.worker_context,"generation",None)
        if generation is not None and generation != self.generation:
            return
        with self.output_lock:
            print(json.dumps(event), flush=True)

    def status(self, state, message):
        self.emit(type="status", state=state, message=message)

    def stop(self):
        self.listening = False
        self.generation += 1
        if self.actions_pending:
            browser.cancel()
        self.actions_pending = 0
        if self.voice is not None:
            voice, self.voice = self.voice, None
            try:
                voice.cancel()
            except Exception as error:
                self.voice = voice
                self.status("error", "Voxtype cancel: " + str(error))
                return
        self.planner = StreamPlanner()
        self.pending = 0
        self.emit(type="activity", state="idle")
        self.emit(type="level", value=0)
        self.status("ready", "Microphone off")

    def listen(self):
        if self.listening:
            return
        from hyprash.speech import VoxtypeSession
        self.stop()
        generation = self.generation
        voice = VoxtypeSession()
        try:
            voice.start()
        except Exception:
            voice.close()
            raise
        self.voice = voice
        self.listening = True
        self.status("listening", "Voxtype · " + voice.model + " · click mic again to finish")
        def watch():
            try:
                started = time.monotonic()
                seen_busy = False
                while generation == self.generation:
                    state = voice.state()
                    if state == "transcribing" and not seen_busy:
                        seen_busy = True
                        self.events.put((generation, {"type":"speech_busy"}))
                    if state == "idle":
                        # State and output are separate writes; tolerate their ordering.
                        for _ in range(10):
                            if voice.path.exists():
                                break
                            time.sleep(.05)
                        text = voice.path.read_text().strip() if voice.path.exists() else ""
                        voice.owned = False
                        self.events.put((generation, {"type":"speech_text", "text":text}))
                        return
                    if state == "stopped" or time.monotonic()-started > 180:
                        raise RuntimeError("Voxtype stopped or timed out")
                    time.sleep(.1)
            except Exception as error:
                self.events.put((generation, {"type":"error", "message":str(error)}))
            finally:
                voice.close()
        threading.Thread(target=watch, daemon=True).start()

    def finish_recording(self):
        if self.voice is not None:
            self.voice.finish()
            self.listening = False
            self.status("processing", "Transcribing with your Voxtype model…")
            self.emit(type="activity", state="transcribing", message="Voxtype is transcribing locally…")

    def run_command(self, args):
        result = subprocess.run(args, capture_output=True, text=True, timeout=12)
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[:180] or f"{args[0]} failed")

    def publish_note(self, show=True):
        DATA.joinpath("notes").mkdir(parents=True, exist_ok=True)
        path = DATA / "notes" / (self.note["id"] + ".json")
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.note, ensure_ascii=False, indent=2))
        temp.replace(path)
        self.emit(type="note" if show else "note_saved", **self.note)

    def ensure_note(self):
        if self.note is None:
            paths = sorted(DATA.glob("notes/*.json"), key=lambda p:p.stat().st_mtime, reverse=True)
            if paths:
                self.note = json.loads(paths[0].read_text())
            else:
                self.note = {"id": uuid.uuid4().hex, "title":"Untitled", "body":""}

    def enqueue_action(self, action):
        if self.action_worker is None:
            def work():
                while True:
                    generation, action = self.action_jobs.get()
                    if generation != self.generation: continue
                    self.worker_context.generation = generation
                    try:
                        self.execute(action)
                    except Exception as error:
                        self.emit(type="action", error=True, message=str(error))
                    self.events.put((generation, {"type":"action_done"}))
            self.action_worker=threading.Thread(target=work,daemon=True)
            self.action_worker.start()
        self.actions_pending += 1
        self.action_jobs.put((self.generation,action))

    def execute(self, action):
        kind, value = action.kind, action.value
        try:
            if kind == "stop":
                self.stop()
                return
            if kind == "web_task":
                message=browser.request(json.loads(value))['message']
            elif kind == "obsidian_note":
                title=desktop.create_obsidian_note(json.loads(value)['content'])
                self.notes_target="obsidian"
                self.external_note_title=title
                message="Saved Obsidian note · "+title
            elif kind == "ui_control":
                task=json.loads(value)
                active=json.loads(browser.run(['hyprctl','-j','activewindow']))
                if active.get('title') in ('Hyprash · Notes','Hyprash · Camera'):
                    self.emit(type="ui_control", window=active['title'], **task)
                    return
                message=desktop.control(task)['message']
            elif kind in ("address", "browser_type", "browser_key"):
                if kind=="browser_key" and value=="new tab":browser.request({'action':'new_tab'})
                else:browser.control(kind, value)
                message = {"address":"Address bar ready", "browser_type":"Typed in address bar", "browser_key":"Browser: " + value}[kind]
            elif kind == "open":
                if value in ("notes","obsidian","hyprash_notes"):
                    if value != "hyprash_notes" and desktop.launch("obsidian" if value=="obsidian" else "notes"):
                        self.notes_target = "obsidian"
                    else:
                        self.notes_target = "hyprash"
                        self.ensure_note()
                        self.publish_note()
                elif value in ("camera","snapshot","hyprash_camera"):
                    if value != "hyprash_camera" and desktop.launch("camera"):
                        self.camera_target = "desktop"
                    else:
                        self.camera_target = "hyprash"
                        self.emit(type="camera", capture=False)
                else:
                    commands = {"browser":["xdg-open", "https://www.google.com"],
                        "terminal":["gtk-launch", "foot"], "files":["gtk-launch", "org.gnome.Nautilus"],
                        "code":["gtk-launch", "code"]}
                    if value in commands:desktop.start_app(commands[value])
                    elif not desktop.launch(value):raise RuntimeError("No installed app named " + value)
                message = f"Opened {value}" if value in ("notes", "camera") else f"Requested {value}"
                if value=="notes" and self.notes_target=="hyprash":
                    message="Opened Hyprash Notes · Obsidian needs a valid vault"
                if value=="obsidian" and self.notes_target=="obsidian":message="Opened Obsidian"
            elif kind == "url":
                from urllib.parse import urlparse, parse_qs
                url=urlparse(value)
                task=({'action':'search','query':parse_qs(url.query)['q'][0]} if url.hostname=='www.google.com' and url.path=='/search' and 'q' in parse_qs(url.query)
                      else {'action':'navigate','url':value})
                message=browser.request(task)['message']
            elif kind in ("new_note", "title", "write"):
                if self.notes_target == "obsidian":
                    if kind == "title":
                        message=desktop.control({'action':'fill','target':'Note title','text':value})['message']
                        self.external_note_title=value
                    else:
                        title=value if kind=='new_note' else self.external_note_title
                        if not title:raise RuntimeError('Create a named note first, or select a field and dictate into it.')
                        desktop.new_obsidian_note(title,value if kind=='write' else '',append=kind=='write')
                        self.external_note_title=title
                        message='Saved Obsidian note · '+self.external_note_title
                    self.emit(type="action",message=message)
                    return
                self.ensure_note()
                if kind == "new_note":
                    self.note = {"id":uuid.uuid4().hex, "title":value, "body":""}
                elif kind == "title":
                    self.note["title"] = value
                else:
                    self.note["body"] += ("\n" if self.note["body"] else "") + value
                self.publish_note()
                message = "Saved note · " + self.note["title"]
            elif kind == "photo":
                if self.camera_target == "desktop":
                    message=desktop.control({'action':'click','target':'Take Picture'})['message']
                else:
                    self.emit(type="camera", capture=True)
                    return
            elif kind == "workspace":
                self.run_command(["hyprctl", "dispatch", f'hl.dsp.focus({{workspace="{value}"}})'])
                message = "Workspace " + value
            else:
                return
            self.emit(type="action", message=message)
        except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as error:
            self.emit(type="action", error=True, message=str(error))

    def start_decisions(self):
        if self.decision_worker is not None:
            return
        def work():
            model = LayaDecision()
            self.events.put((None, {"internal":"engine", "message":"Laya · loading locally"}))
            try:
                model.load()
                self.events.put((None, {"internal":"engine", "message":"Laya · local CPU · offline"}))
            except Exception as error:
                self.events.put((None, {"internal":"engine", "message":"Laya unavailable: " + str(error)}))
                # Requests will get an explicit error; there is no silent regex bypass.
            while True:
                generation, text = self.decisions.get()
                if generation != self.generation: continue
                try:
                    decision = model.decide(text)
                    self.events.put((generation, {"type":"decision", "decision":decision}))
                except Exception as error:
                    self.events.put((generation, {"type":"decision_error", "message":str(error)}))
        self.decision_worker = threading.Thread(target=work, daemon=True)
        self.decision_worker.start()

    def submit_decision(self, text):
        self.start_decisions()
        try:
            self.decisions.put_nowait((self.generation, text))
        except queue.Full:
            self.emit(type="action", error=True, message="Too many pending commands. Wait a moment or press Stop.")
            return
        self.pending += 1
        self.emit(type="activity", state="thinking", message="Laya is deciding locally…")

    def finish_decision(self, event):
        self.pending = max(0, self.pending - 1)
        if event["type"] == "decision_error":
            self.emit(type="action", error=True, message="Laya couldn’t decide: " + event["message"])
        else:
            decision = event["decision"]
            self.emit(type="decision", model="convaiinnovations/laya", intent=decision.intent,
                      probability=decision.probability, elapsed_ms=decision.elapsed_ms)
            if decision.action:
                self.emit(type="activity", state="executing", message="Applying desktop action…")
                self.enqueue_action(decision.action)
            else:
                self.emit(type="action", message=decision.reason)
        self.emit(type="activity", state="executing" if self.actions_pending else "thinking" if self.pending else "idle")

    def transcript(self, text, final):
        self.emit(type="transcript", text=text, final=final)
        if not final:
            return
        # Stop is an immediate control, so a slow/failed model can never trap the mic.
        if text.strip().lower().strip(" .!?,") == "stop listening":
            self.stop()
            return
        normalized = text.lower().replace("dot com", ".com").replace("dot org", ".org")
        normalized = re.sub(r"\s+\.", ".", normalized)
        available = parse(normalized, final)
        actions = self.planner.feed(normalized, final, time.monotonic())
        for action in actions:
            next_offsets = [a.offset for a in available if a.offset > action.offset]
            end = min(next_offsets) if next_offsets else len(normalized)
            clause = normalized[action.offset:end].strip()
            clause = re.sub(r"\s+(?:and(?: then)?|then|can you|and can you)$", "", clause)
            self.submit_decision(clause)
        if final and text and not actions and not available:
            self.submit_decision(text)

    def request(self, request):
        command = request.get("command")
        if command == "listen": self.listen()
        elif command == "stop": self.stop()
        elif command == "finish": self.finish_recording()
        elif command == "text":
            if self.listening or self.voice is not None: self.stop()
            self.transcript(str(request.get("text", ""))[:4000], True)
        elif command == "save_note" and self.note and request.get("id") == self.note["id"]:
            self.note.update(title=str(request.get("title", "Untitled"))[:500], body=str(request.get("body", ""))[:100000])
            self.publish_note(show=False)
        elif command == "theme":
            self.themes.select(str(request.get("name", "")))
            self.emit(type="theme", theme=self.themes.current())
        elif command == "feedback":
            self.emit(type="action", message=str(request.get("message", "")))

    def main(self):
        def read_requests():
            for line in sys.stdin:
                try: self.events.put((None, json.loads(line)))
                except ValueError: pass
            self.events.put((None, {"command":"quit"}))
        threading.Thread(target=read_requests, daemon=True).start()
        self.status("ready", "Ready when you are")
        self.start_decisions()
        next_theme = 0.0
        try:
            while True:
                if time.monotonic() >= next_theme:
                    theme = self.themes.changed()
                    if theme: self.emit(type="theme", theme=theme)
                    next_theme = time.monotonic() + 2
                try:
                    generation, event = self.events.get(timeout=2)
                except queue.Empty:
                    continue
                if generation is None:
                    if event.get("internal") == "engine":
                        self.emit(type="engine", message=event["message"])
                        continue
                    if event.get("command") == "quit": break
                    try: self.request(event)
                    except Exception as error: self.emit(type="action", error=True, message=str(error))
                elif generation == self.generation:
                    if event["type"] in ("decision", "decision_error"):
                        self.finish_decision(event)
                    elif event["type"] == "action_done":
                        self.actions_pending=max(0,self.actions_pending-1)
                        self.emit(type="activity",state="executing" if self.actions_pending else "thinking" if self.pending else "idle")
                    elif event["type"] == "speech_busy":
                        self.listening = False
                        self.status("processing", "Transcribing with your Voxtype model…")
                        self.emit(type="activity", state="transcribing", message="Voxtype is transcribing locally…")
                    elif event["type"] == "speech_text":
                        self.voice = None
                        self.listening = False
                        self.status("ready", "Microphone off")
                        self.emit(type="activity", state="idle")
                        if event["text"]:
                            self.transcript(event["text"], True)
                        else:
                            self.emit(type="action", error=True, message="No speech received from Voxtype. Try recording again.")
                    elif event["type"] == "error":
                        self.stop()
                        self.status("error", event["message"])
        finally:
            self.stop()

if __name__ == "__main__":
    backend = Backend()
    def shutdown(*_):
        backend.stop()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    backend.main()
