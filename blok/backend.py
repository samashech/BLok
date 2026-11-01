"""JSON-lines bridge between Quickshell, local Whisper speech and local Laya decisions."""
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

from blok.commands import StreamPlanner
from blok import browser, desktop
from blok.decision import LayaDecision
from blok.plans import Plan, proposals
from blok.themes import ThemeStore
from blok.nlu import ConversationContext, resolve_intent, normalize_utterance
from blok.diagnostics import StageTimer, record_trace, get_diagnostics_summary
from blok.recording import SessionActionRecorder, compile_routine

ROOT = Path(__file__).resolve().parent.parent
from blok.paths import DATA

class Backend:
    def __init__(self):
        self.output_lock = threading.Lock()
        self.events = queue.Queue()
        self.generation = 0
        self.listening = False
        self.planner = StreamPlanner()
        self.note = None
        self.notes_target = "blok"
        self.camera_target = "blok"
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
        # Follow-up result selection is session-only. It holds tab metadata,
        # never page text, result titles, URLs, or screen captures.
        self.browser_context = None
        from blok.nlu import ConversationContext
        self.context = ConversationContext()
        self.last_execution_report = None
        self.action_recorder = SessionActionRecorder()
        self.recording_routine_name = None
        self.recorded_routine_steps = []
        self.approval_events = {}
        self.approval_results = {}
        self.active_plan_id = None
        self.last_executed_plan = None
        self.laya = None
        # Only the running app probes the desktop and browser; tests and scripts don't.
        self.live = False
        from blok.voice import Speaker
        # Silent until main() runs, so tests and scripts never talk.
        self.speaker = Speaker(DATA / 'settings.json', on_notice=lambda message: self.emit(type="engine", message=message), enabled=False)
        # Session-only file candidates for "open it" / "open file 2" follow-ups.
        self.file_candidates = (0.0, [])

    def emit(self, **event):
        generation=getattr(self.worker_context,"generation",None)
        if generation is not None and generation != self.generation:
            return
        with self.output_lock:
            print(json.dumps(event), flush=True)
        # Talk back: every user-facing result is spoken, except per-step
        # messages inside a plan, which are summarised once at the end.
        if event.get("type") == "action" and getattr(self.worker_context, "in_plan", False):
            self.plan_messages.append(event.get("message", ""))
        elif event.get("type") == "action" and event.get("message"):
            from blok.voice import spoken
            self.speaker.say(spoken(event["message"], error=bool(event.get("error"))))

    def status(self, state, message):
        self.emit(type="status", state=state, message=message)

    def has_pending_approval(self) -> bool:
        return any(not event.is_set() for event in self.approval_events.values())

    def wait_for_approval(self, approval_id: str, timeout: float = 30.0) -> bool:
        event = self.approval_events.get(approval_id)
        if not event:
            return False
        done = event.wait(timeout=timeout)
        generation = getattr(self.worker_context, "generation", self.generation)
        if generation != self.generation:
            self.approval_events.pop(approval_id, None)
            self.approval_results.pop(approval_id, None)
            return False
        result = self.approval_results.get(approval_id, False) if done else False
        self.approval_events.pop(approval_id, None)
        self.approval_results.pop(approval_id, None)
        return result

    def request_approval(self, reason: str, **details) -> bool:
        """Show an approval card and block this worker until approve, reject or 30 s timeout."""
        approval_id = str(uuid.uuid4())
        self.approval_events[approval_id] = threading.Event()
        self.approval_results[approval_id] = False
        self.emit(type="approval_request", approval_id=approval_id, reason=reason, **details)
        self.emit(type="activity", state="awaiting_approval", message="Approval needed: " + reason)
        return self.wait_for_approval(approval_id, timeout=30.0)

    def confirm(self, reason: str, **details):
        if not self.request_approval(reason, **details):
            raise RuntimeError("Not done: " + reason.rstrip("?") + " was rejected or timed out.")

    def resolve_approval(self, approval_id: str, approved: bool):
        if not approval_id:
            return self.resolve_latest_approval(approved)
        if approval_id in self.approval_events:
            self.approval_results[approval_id] = approved
            self.approval_events[approval_id].set()
            self.emit(type="approval_resolved", approval_id=approval_id, approved=approved)
            return True
        return False

    def resolve_latest_approval(self, approved: bool):
        for approval_id, event in reversed(list(self.approval_events.items())):
            if not event.is_set():
                self.approval_results[approval_id] = approved
                event.set()
                self.emit(type="approval_resolved", approval_id=approval_id, approved=approved)
                return True
        return False

    def cancel_all_approvals(self):
        for approval_id, event in list(self.approval_events.items()):
            self.approval_results[approval_id] = False
            event.set()
        self.approval_events.clear()
        self.approval_results.clear()

    def stop(self):
        self.speaker.stop()
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
                self.status("error", "Microphone cancel: " + str(error))
                return
        self.planner = StreamPlanner()
        self.pending = 0
        if not self.context.is_search_context_valid():
            self.browser_context = None
            self.context.clear_search_context()
        self.cancel_all_approvals()
        self.emit(type="activity", state="idle")
        self.emit(type="level", value=0)
        self.status("ready", "Microphone off")

    def listen(self):
        if self.listening:
            return
        from blok.speech import new_session
        self.stop()
        generation = self.generation
        voice = new_session()
        try:
            voice.start()
        except Exception:
            voice.close()
            raise
        self.voice = voice
        self.listening = True
        self.status("listening", voice.model + " · local · click mic again to finish")
        def watch():
            try:
                text = voice.wait(lambda: generation == self.generation,
                                  on_busy=lambda: self.events.put((generation, {"type": "speech_busy"})))
                if text is not None:
                    self.events.put((generation, {"type": "speech_text", "text": text}))
            except Exception as error:
                self.events.put((generation, {"type": "error", "message": str(error)}))
            finally:
                voice.close()
        threading.Thread(target=watch, daemon=True).start()

    def finish_recording(self):
        if self.voice is not None:
            self.voice.finish()
            self.listening = False
            self.status("processing", "Transcribing locally…")
            self.emit(type="activity", state="transcribing", message="Whisper is transcribing locally…")

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
                        if isinstance(action, Plan):
                            self.execute_plan(action)
                        else:
                            self.execute(action)
                    except Exception as error:
                        self.emit(type="action", error=True, message=str(error))
                    self.events.put((generation, {"type":"action_done"}))
            self.action_worker=threading.Thread(target=work,daemon=True)
            self.action_worker.start()
        self.actions_pending += 1
        self.action_jobs.put((self.generation,action))

    def step_label(self, action):
        if action.kind == 'web_task':
            from blok.workflows import task_label
            return task_label(json.loads(action.value))
        if action.kind == 'tool':
            from blok.router import label
            return label(json.loads(action.value))
        if action.kind == 'routine':
            from blok.routines import get_routine
            routine = get_routine(action.value, DATA)
            return routine.description if routine else f"Run routine {action.value}"
        labels = {'open': 'Open ', 'new_note': 'Create note ', 'title': 'Title note ',
                  'write': 'Write note ', 'photo': 'Take photo', 'workspace': 'Switch workspace ',
                  'address': 'Focus address bar', 'browser_type': 'Type in browser',
                  'browser_key': 'Use browser key ', 'url': 'Open web page ',
                  'obsidian_note': 'Create Obsidian note'}
        return labels.get(action.kind, 'Run action ') + (action.value if action.kind in ('open', 'workspace', 'browser_key') else '')


    def _record_executed_action(self, action):
        self.action_recorder.record(action, label=self.step_label(action))
        if self.recording_routine_name:
            self.recorded_routine_steps.append(action)

    def emit_timeline(self, plan_id: str, status: str, timeline_steps: list[dict]):
        self.emit(
            type="timeline_update",
            plan_id=plan_id,
            status=status,
            steps=[dict(s) for s in timeline_steps],
        )

    def execute_plan(self, plan):
        self.worker_context.in_plan = True
        self.plan_messages = []
        try:
            ok = self._execute_plan(plan)
        finally:
            self.worker_context.in_plan = False
        from blok.voice import spoken
        said = [m for m in self.plan_messages if m]
        if said:
            summary = said[-1] if not ok else (', then '.join(said[-2:]) if len(said) > 1 else said[0])
            self.speaker.say(spoken(summary, error=not ok))
        return ok

    def _execute_plan(self, plan):
        from blok.plans import PlanExecutionReport
        generation = getattr(self.worker_context, "generation", self.generation)
        total = len(plan.steps)
        failed_step_ids = set()
        completed_step_ids = []
        skipped_step_ids = []
        step_outputs = {}
        plan_id = uuid.uuid4().hex[:8]
        self.active_plan_id = plan_id
        self.last_executed_plan = plan

        timeline_steps = [
            {
                "step_id": getattr(s, "step_id", f"step_{i}"),
                "subtask_id": getattr(s, "subtask_id", f"subtask_{i}"),
                "kind": s.kind,
                "value": s.value,
                "label": self.step_label(s),
                "domain": getattr(s, "target_domain", "general"),
                "risk_level": getattr(s, "risk_level", "SAFE_READ"),
                "requires_approval": getattr(s, "requires_approval", False),
                "status": "pending",
                "duration_ms": 0,
            }
            for i, s in enumerate(plan.steps, 1)
        ]
        self.emit_timeline(plan_id, "running", timeline_steps)

        for index, action in enumerate(plan.steps, 1):
            sid = getattr(action, 'step_id', f'step_{index}')
            current_step_item = timeline_steps[index - 1]

            if generation != self.generation:
                self.emit(type='activity', state='cancelled', message='Plan cancelled.')
                current_step_item["status"] = "skipped"
                self.emit_timeline(plan_id, "cancelled", timeline_steps)
                self.last_execution_report = PlanExecutionReport(
                    completed_steps=completed_step_ids,
                    failed_steps=[{'step_id': s, 'stage': 'act'} for s in failed_step_ids],
                    skipped_steps=skipped_step_ids,
                    overall_status="cancelled"
                )
                return False

            # Check dependencies: if any predecessor failed, skip this step
            failed_deps = [d for d in getattr(action, 'depends_on', ()) if d in failed_step_ids]
            if failed_deps:
                failed_step_ids.add(sid)
                skipped_step_ids.append(sid)
                current_step_item["status"] = "skipped"
                self.emit_timeline(plan_id, "running", timeline_steps)
                self.emit(type='activity', state='executing',
                          message=f'Step {index} of {total} · Skipped {self.step_label(action)} (predecessor failed)')
                continue

            target_step = action
            input_binds = getattr(action, 'input_bindings_dict', {})
            if input_binds:
                for param, bind_key in input_binds.items():
                    if bind_key in step_outputs:
                        if param == "target_tab_id":
                            from dataclasses import replace
                            target_step = replace(action, target_tab_id=step_outputs[bind_key])

            # HITL Approval Gate
            if getattr(action, 'requires_approval', False):
                current_step_item["status"] = "awaiting_approval"
                self.emit_timeline(plan_id, "awaiting_approval", timeline_steps)
                approved = self.request_approval(
                    getattr(action, "approval_reason", "") or "Sensitive action requires approval",
                    action=action.kind, value=action.value, plan_id=plan_id, step_id=sid,
                    risk_level=getattr(action, "risk_level", "SENSITIVE_DESTRUCTIVE"),
                    domain=getattr(action, "target_domain", "general"))
                if not approved:
                    failed_step_ids.add(sid)
                    current_step_item["status"] = "failed"
                    self.emit_timeline(plan_id, "failed", timeline_steps)
                    self.emit(type="action", error=True, message=f"Action '{self.step_label(action)}' was rejected or timed out.")
                    self.last_execution_report = PlanExecutionReport(
                        completed_steps=completed_step_ids,
                        failed_steps=[{'step_id': s, 'stage': 'act'} for s in failed_step_ids],
                        skipped_steps=skipped_step_ids,
                        overall_status="failed"
                    )
                    return False

            current_step_item["status"] = "running"
            self.emit_timeline(plan_id, "running", timeline_steps)
            self.emit(type='activity', state='step_started',
                      message=f'Step {index} of {total} · {self.step_label(target_step)}')
            self.emit(type='activity', state='acting',
                      message=f'Step {index} of {total} · {self.step_label(target_step)}')

            t_start = time.monotonic()
            step_ok = self.execute(target_step)
            dur_ms = int((time.monotonic() - t_start) * 1000)
            current_step_item["duration_ms"] = dur_ms

            if not step_ok:
                failed_step_ids.add(sid)
                current_step_item["status"] = "failed"
                # Determine if remaining steps can proceed
                remaining_steps = plan.steps[index:]
                can_continue = False
                if getattr(action, 'on_failure', 'ABORT_ALL') == 'ABORT_DEPENDENT' and remaining_steps:
                    independent_remaining = [
                        s for s in remaining_steps
                        if not any(d in failed_step_ids for d in getattr(s, 'depends_on', ()))
                        and getattr(s, 'target_domain', 'general') != getattr(action, 'target_domain', 'general')
                    ]
                    if independent_remaining:
                        can_continue = True

                if not can_continue:
                    if generation == self.generation:
                        self.emit(type='action', error=True,
                                  message=f'Stopped at step {index} of {total}; later steps were not run.')
                        self.emit(type='activity', state='failed',
                                  message=f'Stopped at step {index} of {total}')
                    self.emit_timeline(plan_id, "failed", timeline_steps)
                    self.last_execution_report = PlanExecutionReport(
                        completed_steps=completed_step_ids,
                        failed_steps=[{'step_id': s, 'stage': 'act'} for s in failed_step_ids],
                        skipped_steps=skipped_step_ids,
                        overall_status="failed"
                    )
                    return False
            else:
                completed_step_ids.append(sid)
                current_step_item["status"] = "verified"
                self.emit_timeline(plan_id, "running", timeline_steps)
                if getattr(action, 'output_binding', None) == "tab_id":
                    tab_id = self.context.active_tab_id or (self.browser_context and self.browser_context.get('tabId'))
                    if tab_id:
                        step_outputs[f"{getattr(action, 'step_id', f'step_{index}')}.tab_id"] = tab_id

        if failed_step_ids:
            self.emit(type='activity', state='failed', message='Plan finished with partial failures.')
            self.emit_timeline(plan_id, "partial_failure", timeline_steps)
            self.last_execution_report = PlanExecutionReport(
                completed_steps=completed_step_ids,
                failed_steps=[{'step_id': s, 'stage': 'act'} for s in failed_step_ids],
                skipped_steps=skipped_step_ids,
                overall_status="partial_failure"
            )
            return False

        self.emit(type='activity', state='succeeded', message='Plan completed successfully.')
        self.emit_timeline(plan_id, "completed", timeline_steps)
        self.last_execution_report = PlanExecutionReport(
            completed_steps=completed_step_ids,
            failed_steps=[],
            skipped_steps=[],
            overall_status="completed"
        )
        return True

    def execute(self, action):
        kind, value = action.kind, action.value
        try:
            if kind == "stop":
                self.stop()
                return True
            if kind == "web_task":
                task_data = json.loads(value)
                if getattr(action, "target_tab_id", None):
                    task_data["target_tab_id"] = action.target_tab_id
                message=self.browser_task(task_data)
            elif kind == "tool":
                message=self.run_tool(json.loads(value))
            elif kind == "obsidian_note":
                title=desktop.create_obsidian_note(json.loads(value)['content'])
                self.notes_target="obsidian"
                self.external_note_title=title
                message="Saved Obsidian note · "+title
            elif kind == "ui_control":
                task=json.loads(value)
                active=json.loads(browser.run(['hyprctl','-j','activewindow']))
                if active.get('title') in ('BLoK · Notes','BLoK · Camera'):
                    self.emit(type="ui_control", window=active['title'], **task)
                    self._record_executed_action(action)
                    return True
                if browser.BROWSERS.fullmatch(active.get('class','')):
                    message=self.click_pointer() if task.get('pointer') else self.browser_task(task)
                elif task.get('pointer'):
                    raise RuntimeError('Pointing works in the browser. In other apps, say the button name, like "click Save".')
                else:
                    observation=desktop.inspect()
                    control=desktop.select_control(observation,task)
                    result=desktop.control({**task,'control':control},owner=observation['owner'])
                    self.emit(type="execution",verified=result.get('verified',False),
                              evidence=result.get('evidence',''),trace=[])
                    message=result['message']
            elif kind in ("address", "browser_type", "browser_key"):
                if kind=="browser_key" and value=="new tab":self.browser_task({'action':'new_tab'})
                else:browser.control(kind, value)
                message = {"address":"Address bar ready", "browser_type":"Typed in address bar", "browser_key":"Browser: " + value}[kind]
            elif kind == "open":
                if value in ("notes","obsidian","blok_notes"):
                    if value != "blok_notes" and desktop.launch("obsidian" if value=="obsidian" else "notes"):
                        self.notes_target = "obsidian"
                    else:
                        self.notes_target = "blok"
                        self.ensure_note()
                        self.publish_note()
                elif value in ("camera","snapshot","blok_camera"):
                    if value != "blok_camera" and desktop.launch("camera"):
                        self.camera_target = "desktop"
                    else:
                        self.camera_target = "blok"
                        self.emit(type="camera", capture=False)
                else:
                    commands = {"browser":["xdg-open", "https://www.google.com"],
                        "terminal":["gtk-launch", "foot"], "files":["gtk-launch", "org.gnome.Nautilus"],
                        "code":["gtk-launch", "code"]}
                    if value in commands:desktop.start_app(commands[value])
                    elif not desktop.launch(value):raise RuntimeError("No installed app named " + value)
                message = f"Opened {value}" if value in ("notes", "camera") else f"Requested {value}"
                if value=="notes" and self.notes_target=="blok":
                    message="Opened BLoK Notes · Obsidian needs a valid vault"
                if value=="obsidian" and self.notes_target=="obsidian":message="Opened Obsidian"
            elif kind == "url":
                from urllib.parse import urlparse, parse_qs
                url=urlparse(value)
                task=({'action':'search','query':parse_qs(url.query)['q'][0]} if url.hostname=='www.google.com' and url.path=='/search' and 'q' in parse_qs(url.query)
                      else {'action':'navigate','url':value})
                message=self.browser_task(task)
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
                    self._record_executed_action(action)
                    return True
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
                    self._record_executed_action(action)
                    return True
            elif kind == "workspace":
                self.run_command(["hyprctl", "dispatch", f'hl.dsp.focus({{workspace="{value}"}})'])
                message = "Workspace " + value
            elif kind == "routine":
                from blok.routines import get_routine, check_routine_preconditions
                routine = get_routine(value, DATA)
                if not routine:
                    raise RuntimeError(f"Routine '{value}' does not exist.")
                ok, failure_reason = check_routine_preconditions(routine, self)
                if not ok:
                    raise RuntimeError(f"Precondition failed for routine '{routine.name}': {failure_reason}")
                self.emit(type="activity", state="executing",
                          message=f"Starting routine · {routine.name}")
                total = len(routine.steps)
                generation = getattr(self.worker_context, "generation", self.generation)
                for index, step in enumerate(routine.steps, 1):
                    if generation != self.generation:
                        return False
                    self.emit(type="activity", state="executing",
                              message=f"Routine {routine.name} · Step {index} of {total} · {self.step_label(step)}")
                    if not self.execute(step):
                        if generation == self.generation:
                            self.emit(type="action", error=True,
                                      message=f"Routine '{routine.name}' stopped at step {index} of {total}; later steps were not run.")
                        return False
                message = f"Completed routine · {routine.name}"
            else:
                return False
            self.emit(type="action", message=message)
            self._record_executed_action(action)
            return True
        except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as error:
            if isinstance(error,browser.BrowserTaskError):
                self.emit(type="execution",verified=False,trace=error.trace)
            self.emit(type="action", error=True, message=str(error))
            return False

    def remember_files(self, paths):
        self.file_candidates = (time.monotonic(), list(paths))

    def recent_file(self, index=1):
        created, paths = self.file_candidates
        if not paths or time.monotonic() - created > 300:
            raise RuntimeError('No recent file list. Say "find <file>" first.')
        if not 1 <= index <= len(paths):
            raise RuntimeError(f'There are only {len(paths)} files in the last list.')
        return paths[index - 1]

    def resolve_path(self, query, kind=None, text_only=False):
        """One concrete path for a spoken description; Laya picks among close matches."""
        from blok import files
        if re.fullmatch(r'(?:it|that|this|that file|this file|that one)', query.strip(), re.I):
            return self.recent_file(1)
        paths = files.find(query, kind=kind)
        if text_only:
            paths = [p for p in paths if p.suffix.lower() in files.TEXT_SUFFIXES]
        if not paths:
            raise files.FileError(f'No {"folder" if kind == "d" else "file"} in your home folder matches "{query}".')
        winner = files.clear_winner(paths, query)
        if winner:
            return winner
        options = {files.display(p): p for p in paths[:8]}
        if self.laya is not None and self.laya.agent is not None:
            choice, _ = self.laya.pick(query, list(options), 'Which of these files is the user talking about?', threshold=0.6)
            if choice:
                return options[choice]
        self.remember_files(list(options.values()))
        listing = '; '.join(f'{i}) {name}' for i, name in enumerate(options, 1))
        raise files.FileError(f'Several match: {listing}. Say "open file 2", or use a fuller name.')

    def run_tool(self, task):
        from blok import files, system
        name = task.get('tool')
        if name == 'answer':
            return system.answer(task['topic'])
        if name == 'volume':
            return system.volume(task['op'], task.get('level'))
        if name == 'brightness':
            return system.brightness(task['op'], task.get('level'))
        if name == 'media':
            return system.media(task['op'])
        if name == 'lock':
            return system.lock()
        if name == 'plugin':
            from blok import plugins
            item = plugins.commands().get(task.get('name', ''))
            if item is None:
                raise RuntimeError(f'The "{task.get("name")}" command is no longer installed.')
            if item.confirm:
                self.confirm(item.description + '?', action='plugin', value=item.name)
            return plugins.run(item, task.get('args', {}))
        if name == 'theme':
            self.themes.select(task.get('name', 'next'))
            theme = self.themes.current()
            self.emit(type="theme", theme=theme)
            return theme['name'] + ' theme'
        if name == 'window':
            return system.window(task['op'], task.get('workspace'), task.get('app'))
        if name == 'download':
            return self.download(task)
        if name == 'file_pick':
            path = self.recent_file(int(task.get('index', 1)))
            return files.open_path(path)
        if name == 'file_find':
            paths = files.find(task['query'])
            if not paths:
                raise files.FileError(f'Nothing in your home folder matches "{task["query"]}".')
            self.remember_files(paths)
            if len(paths) == 1 and paths[0].is_dir() and paths[0] in files.user_dirs().values():
                return files.list_folder(paths[0])
            if len(paths) == 1:
                return f'Found {files.display(paths[0])}. Say "open it" to open it.'
            listing = '; '.join(f'{i}) {files.display(p)}' for i, p in enumerate(paths[:5], 1))
            return f'Found {len(paths)}: {listing}. Say "open file 2" to open one.'
        if name == 'file_create':
            folder = self.resolve_path(task['folder'], kind='d') if task.get('folder') else None
            path = files.create_file(task['name'], folder, task.get('content', ''))
            self.remember_files([path])
            return 'Created ' + files.display(path)
        path = self.resolve_path(task['query'], text_only=name == 'file_append')
        self.remember_files([path])
        if name == 'file_open':
            return files.open_path(path)
        if name == 'file_read':
            return files.display(path) + ': ' + files.read_text(path)
        if name == 'file_append':
            return files.append_text(path, task['text'])
        if name == 'file_rename':
            self.confirm(f'Rename {files.display(path)} to {task["name"]}?', action='file_rename', value=str(path))
            return files.rename(path, task['name'])
        if name in ('file_move', 'file_copy'):
            folder = self.resolve_path(task['dest'], kind='d')
            verb = 'Copy' if name == 'file_copy' else 'Move'
            self.confirm(f'{verb} {files.display(path)} to {files.display(folder)}?', action=name, value=str(path))
            return files.move(path, folder, copy=name == 'file_copy')
        if name == 'file_delete':
            self.confirm(f'Move {files.display(path)} to the trash?', action=name, value=str(path))
            return files.trash(path)
        raise RuntimeError('Unsupported tool: ' + str(name))

    EXTENSION_VERSIONS = ('phase7-v1', 'phase8-v1')

    def require_extension(self, feature, minimum='phase7-v1'):
        version = browser.ping().get('version')
        if version not in self.EXTENSION_VERSIONS[self.EXTENSION_VERSIONS.index(minimum):]:
            raise RuntimeError(f'{feature}: this needs the updated browser extension. Open brave://extensions, click Reload on '
                               f'BLoK, then reload the page (running: {version}).')

    def click_pointer(self):
        """Click the control under the mouse ("click that button"), confirming risky labels first."""
        from blok.plans import SENSITIVE_WORDS
        self.require_extension('Pointing', 'phase8-v1')
        found = browser.request({'action': 'pointer'})
        name = (found.get('name') or '').strip() or 'that control'
        if SENSITIVE_WORDS.search(name):
            self.confirm(f'Click "{name[:60]}"?', action='click', value=name)
        result = browser.request({'action': 'click_observed', 'control': found['control'], 'page': found['page']})
        self.emit(type="execution", verified=result.get('verified', False), evidence=result.get('evidence', ''), trace=result.get('trace', []))
        return 'Clicked ' + name[:80]

    def refresh_page_context(self):
        """Before each command, learn which page is really in front of the user.

        Follow-ups like "search for phantom blade" on Steam or "get me a video" on
        YouTube depend on it, including pages the user opened by hand.
        """
        try:
            active = json.loads(browser.run(['hyprctl', '-j', 'activewindow']) or '{}')
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
            return
        if not browser.BROWSERS.fullmatch(active.get('class', '')):
            # A terminal or editor is in front: browser follow-ups no longer apply.
            self.context.active_site = None
            return
        for request in ({'action': 'active'}, {'action': 'inspect'}):
            try:
                tab = browser.request(request, timeout=2)
            except RuntimeError:
                continue
            url = tab.get('url') or (tab.get('observation') or {}).get('url')
            if url:
                self.context.update_tab(tab.get('tabId') or tab.get('tab_id'), url=url)
                return

    def download(self, task):
        """Search → open the chosen page → Laya picks the download link → approval → verified download."""
        from urllib.parse import urlparse, quote_plus
        progress = lambda event: self.emit(type="activity", state="executing", message=event['message']) if event.get('status') == 'running' else None
        self.require_extension('Downloads')
        if task.get('url'):
            url = task['url']
            self.confirm(f'Download {url}?', action='download', value=url)
            result = browser.request({'action': 'download', 'url': url}, on_progress=progress)
            self.emit(type="execution", verified=result.get('verified', False), evidence=result.get('evidence', ''), trace=result.get('trace', []))
            return result['message']
        query = task['query'].strip()
        steam = re.search(r'\s+(?:on|from) steam$', query, re.I)
        if steam:
            query = query[:steam.start()]
            browser.request({'action': 'navigate', 'url': 'https://store.steampowered.com/search/?term=' + quote_plus(query)}, on_progress=progress)
            return f'Opened Steam store results for {query}. Pick the game and install it from Steam.'
        if self.laya is None or self.laya.agent is None:
            raise RuntimeError('Laya is still loading. Try the download again in a moment.')
        try:
            links = browser.request({'action': 'links', 'query': query, 'download': True}, on_progress=progress)
        except browser.BrowserTaskError:
            links = {}
        # Only trust the current page when it is about the requested thing.
        words = [w for w in re.findall(r'\w+', query.lower()) if len(w) > 2]
        if not any(w in (links.get('title', '') + ' ' + links.get('url', '')).lower() for w in words):
            links = {}
        if not links.get('links'):
            browser.request({'action': 'search', 'site': 'google', 'query': query + ' download'}, on_progress=progress)
            results = browser.request({'action': 'links', 'results': True}, on_progress=progress).get('links', [])
            if not results:
                raise RuntimeError('Google showed no results to choose from.')
            options = {f'{r["name"][:80]} — {urlparse(r["href"]).hostname}': r for r in results[:8]}
            choice, _ = self.laya.pick(f'official download page for {query}', list(options),
                                       f'Which search result is the official download page for {query}?', threshold=0.3)
            chosen = options[choice] if choice else results[0]
            browser.request({'action': 'navigate', 'url': chosen['href']}, on_progress=progress)
            links = browser.request({'action': 'links', 'query': query, 'download': True}, on_progress=progress)
        candidates = links.get('links', [])
        if not candidates:
            return f'Opened {links.get("url", "the page")}, but it shows no download link. Say "click <button name>" to continue.'
        options = {f'{c["name"][:90]}' + (f' ({urlparse(c["href"]).hostname})' if c.get('href') else ''): c for c in candidates[:8]}
        choice, _ = self.laya.pick(f'download {query}', list(options), f'Which link downloads {query}?', threshold=0.3)
        if not choice:
            listing = '; '.join(list(options)[:4])
            return f'Not sure which link downloads {query}. Visible options: {listing}. Say "click <name>".'
        link = options[choice]
        host = urlparse(link.get('href') or links.get('url', '')).hostname or 'this page'
        self.confirm(f'Download from {host}: "{link["name"][:80]}"?', action='download', value=link.get('href', ''))
        result = browser.request({'action': 'click_download', 'control': link['control'], 'page': links['page']}, on_progress=progress)
        self.emit(type="execution", verified=result.get('verified', False), evidence=result.get('evidence', ''), trace=result.get('trace', []))
        return result['message']

    def browser_task(self, task):
        action=task.get('action')
        if action == 'result':
            task={**task,'context':self.require_browser_context()}
        else:
            # A new browser action supersedes a prior search result list.
            self.browser_context=None
        def progress(event):
            if event.get('status') == 'running':
                self.emit(type="activity", state="executing", message=event['message'])
        result=browser.request(task,on_progress=progress)
        if action in ('new_tab', 'navigate', 'search', 'play', 'next_track') and result.get('verified'):
            tab_id = result.get('tab_id') or result.get('tabId')
            url = result.get('url') or task.get('url')
            site = task.get('site')
            if tab_id or url or site:
                self.context.update_tab(tab_id, url=url, site=site)
        if action == 'search' and result.get('verified') and task.get('site') in ('google','youtube'):
            context=result.get('context')
            if context and (context.get('tabId') == result.get('tabId') or context.get('tab_id') == result.get('tab_id')) and context.get('url') == result.get('url'):
                self.browser_context={**context,'created_at':time.monotonic()}
                self.context.set_search_context(result.get('tabId') or result.get('tab_id'), result.get('url'), task.get('site'), task.get('query'))
        elif action == 'result':
            self.browser_context=None
            self.context.clear_search_context()
        self.emit(type="execution",verified=result.get('verified',False),
                  evidence=result.get('evidence',''),trace=result.get('trace',[]))
        return result['message']

    def require_browser_context(self):
        context=self.browser_context
        if not context or time.monotonic()-context['created_at'] > 300:
            self.browser_context=None
            self.context.clear_search_context()
            raise RuntimeError('No current search results. Search Google or YouTube, then choose a result within five minutes.')
        observation=browser.request({'action':'inspect'},on_progress=lambda event:None)
        if (observation.get('tabId') != context['tabId'] or observation.get('url') != context['url']):
            self.browser_context=None
            self.context.clear_search_context()
            raise RuntimeError('Those search results are no longer current. Search again before choosing a result.')
        return {key:context[key] for key in ('tabId','url','site','query')}

    @staticmethod
    def has_result_followup(candidates):
        return any(action and action.kind=='web_task' and json.loads(action.value).get('action')=='result'
                   for _,action in candidates)

    def plan_with_rephrase(self, model, generation, text, timer):
        """Let a local Ollama model restate casual speech; the rewrite still goes through rules and Laya.

        Returns a runnable decision from the rewrite, a decision carrying the model's
        clarifying question when neither wording works, or None to plan `text` as said.
        """
        from blok import rephrase
        rewrite = rephrase.rewrite(text)
        if rewrite is None or generation != self.generation:
            return None
        if timer:
            timer.record_stage('rephrase_ms', rewrite.elapsed_ms)
        if rewrite.command and rewrite.command.lower() != text.lower().strip(' .!?'):
            self.events.put((generation, {"type": "understood", "text": rewrite.command, "model": rewrite.model}))
            try:
                decision = model.plan(rewrite.command, self.context)
            except ValueError:
                decision = None
            if decision is not None and decision.action is not None:
                return decision
        if rewrite.question:
            try:
                decision = model.plan(text, self.context)
            except ValueError:
                decision = None
            if decision is not None and decision.action is not None:
                return decision
            from blok.decision import Decision
            return Decision(None, 'clarify', 0.0, rewrite.elapsed_ms, rewrite.question)
        return None

    def start_decisions(self):
        if self.decision_worker is not None:
            return
        def work():
            model = LayaDecision()
            self.laya = model
            self.events.put((None, {"internal":"engine", "message":"Laya · loading locally"}))
            try:
                model.load()
                self.events.put((None, {"internal":"engine", "message":"Laya · local CPU · offline"}))
                from blok import rephrase
                rephrase.warm_up()
            except Exception as error:
                self.events.put((None, {"internal":"engine", "message":"Laya unavailable: " + str(error)}))
            while True:
                item = self.decisions.get()
                generation = item[0]
                text = item[1]
                timer = item[2] if len(item) > 2 else None
                intent = item[3] if len(item) > 3 else None
                if generation != self.generation: continue
                try:
                    decision = self.plan_with_rephrase(model, generation, text, timer)
                    t_inf = time.monotonic_ns()
                    decision = decision or model.plan(text, self.context)
                    inf_ms = (time.monotonic_ns() - t_inf) / 1_000_000.0
                    if timer:
                        timer.record_stage('laya_inference_ms', inf_ms)
                    self.events.put((generation, {"type":"decision", "decision":decision, "timer":timer, "intent":intent}))
                except Exception as error:
                    self.events.put((generation, {"type":"decision_error", "message":str(error), "timer":timer, "intent":intent}))
        self.decision_worker = threading.Thread(target=work, daemon=True)
        self.decision_worker.start()

    def submit_decision(self, text):
        timer = StageTimer()
        with timer.measure('nlu_normalize_ms'):
            intent = resolve_intent(text, self.context)

        if intent.intent_type == "cancel":
            self.emit(type="action", message="Request cancelled; no action taken")
            record_trace(text, intent.normalized_text, "rule", "cancel", 1.0, [], "cancelled", timer.finish())
            return
        if intent.intent_type == "unsupported":
            self.emit(type="action", error=True, message=intent.ambiguity_reason or "Unsupported step. Nothing was run.")
            record_trace(text, intent.normalized_text, "rule", "unsupported", 0.0, [], "failed", timer.finish(), error=intent.ambiguity_reason)
            return
        if intent.requires_clarification:
            self.emit(type="activity", state="clarifying", message=intent.ambiguity_reason)
            self.emit(type="action", message=intent.ambiguity_reason)
            record_trace(text, intent.normalized_text, "rule", "clarify", 0.5, [], "clarifying", timer.finish(), ambiguity_reason=intent.ambiguity_reason)
            return
        if intent.intent_type in ("hitl_approve", "hitl_reject"):
            if self.has_pending_approval():
                approved = (intent.intent_type == "hitl_approve")
                self.resolve_latest_approval(approved)
            else:
                self.emit(type="action", message="No pending action requires approval.")
            return
        if intent.intent_type == "start_recording_routine":
            name = intent.slots.get("name") or "custom_routine"
            self.recording_routine_name = name
            self.recorded_routine_steps = []
            self.emit(type="recording_started", name=name)
            self.emit(type="action", message=f"Started recording routine '{name}'. Perform your actions, then say 'stop recording'.")
            record_trace(text, intent.normalized_text, "rule", "start_recording_routine", 1.0, [], "succeeded", timer.finish())
            return
        if intent.intent_type == "stop_recording_routine":
            if not self.recording_routine_name:
                self.emit(type="action", message="No active routine recording to stop.")
                record_trace(text, intent.normalized_text, "rule", "stop_recording_routine", 1.0, [], "succeeded", timer.finish())
                return
            name = self.recording_routine_name
            steps = list(self.recorded_routine_steps)
            self.recording_routine_name = None
            self.recorded_routine_steps = []
            if not steps:
                self.emit(type="action", error=True, message=f"No actions were executed during recording '{name}'. Routine not saved.")
                return
            try:
                routine = compile_routine(name, steps, data_dir=DATA)
                self.emit(type="routine_saved", routine=routine.to_dict())
                self.emit(type="action", message=f"Saved routine '{routine.name}' with {len(routine.steps)} steps.")
                record_trace(text, intent.normalized_text, "rule", "stop_recording_routine", 1.0, [self.step_label(s) for s in steps], "succeeded", timer.finish())
            except Exception as error:
                self.emit(type="action", error=True, message=f"Failed to save routine '{name}': {error}")
            return
        if intent.intent_type == "save_recent_routine":
            name = intent.slots.get("name") or "recent_routine"
            steps = []
            if self.last_executed_plan and self.last_executed_plan.steps:
                steps = list(self.last_executed_plan.steps)
            elif self.action_recorder:
                steps = self.action_recorder.get_last_n(5)
            if not steps:
                self.emit(type="action", error=True, message="No recent actions found to save as a routine.")
                return
            try:
                routine = compile_routine(name, steps, data_dir=DATA)
                self.emit(type="routine_saved", routine=routine.to_dict())
                self.emit(type="action", message=f"Saved recent actions as routine '{routine.name}' with {len(routine.steps)} steps.")
                record_trace(text, intent.normalized_text, "rule", "save_recent_routine", 1.0, [self.step_label(s) for s in steps], "succeeded", timer.finish())
            except Exception as error:
                self.emit(type="action", error=True, message=f"Failed to save routine '{name}': {error}")
            return

        try:
            with timer.measure('plan_validation_ms'):
                candidates = proposals(text, self.context)
                if self.has_result_followup(candidates):
                    self.require_browser_context()
        except ValueError as error:
            self.emit(type="action", error=True, message=str(error))
            record_trace(text, text, "rule", "error", 0.0, [], "failed", timer.finish(), error=str(error))
            return
        except RuntimeError as error:
            self.emit(type="action", error=True, message=str(error))
            record_trace(text, text, "rule", "error", 0.0, [], "failed", timer.finish(), error=str(error))
            return

        all_resolved = all(action is not None for _, action in candidates)
        if all_resolved and intent.confidence >= 0.90:
            plan = Plan(tuple(action for _, action in candidates))
            timer.record_stage('laya_inference_ms', 0.0)
            self.emit(type="decision", model="rule-engine", intent=intent.intent_type,
                      probability=intent.confidence, elapsed_ms=0)
            self.emit(type="activity", state="validating", message="Validated plan upfront…")
            record_trace(text, intent.normalized_text, "rule", intent.intent_type, intent.confidence,
                         [self.step_label(s) for s in plan.steps], "succeeded", timer.finish())
            self.enqueue_action(plan)
            return

        self.start_decisions()
        try:
            self.decisions.put_nowait((self.generation, text, timer, intent))
        except queue.Full:
            self.emit(type="action", error=True, message="Too many pending commands. Wait a moment or press Stop.")
            return
        self.pending += 1
        self.emit(type="activity", state="thinking", message="Laya is deciding locally…")

    def finish_decision(self, event):
        self.pending = max(0, self.pending - 1)
        timer = event.get("timer")
        intent = event.get("intent")
        if event["type"] == "decision_error":
            self.emit(type="action", error=True, message="Laya couldn’t decide: " + event["message"])
            if timer:
                record_trace(intent.raw_text if intent else "", intent.normalized_text if intent else "",
                             "laya", "error", 0.0, [], "failed", timer.finish(), error=event["message"])
        else:
            decision = event["decision"]
            self.emit(type="decision", model="convaiinnovations/laya", intent=decision.intent,
                      probability=decision.probability, elapsed_ms=decision.elapsed_ms)
            if decision.action:
                self.emit(type="activity", state="executing", message="Applying desktop action…")
                if timer:
                    steps = [self.step_label(s) for s in decision.action.steps] if isinstance(decision.action, Plan) else [self.step_label(decision.action)]
                    record_trace(intent.raw_text if intent else "", intent.normalized_text if intent else "",
                                 "laya", decision.intent, decision.probability, steps, "succeeded", timer.finish())
                self.enqueue_action(decision.action)
            else:
                self.emit(type="action", message=decision.reason)
                if timer:
                    record_trace(intent.raw_text if intent else "", intent.normalized_text if intent else "",
                                 "laya", decision.intent, decision.probability, [], "failed", timer.finish(), ambiguity_reason=decision.reason)
        self.emit(type="activity", state="executing" if self.actions_pending else "thinking" if self.pending else "idle")

    def transcript(self, text, final):
        self.emit(type="transcript", text=text, final=final)
        if not final:
            return
        # Stop is an immediate control, so a slow/failed model can never trap the mic.
        if text.strip().lower().strip(" .!?,") == "stop listening":
            self.stop()
            return
        if not text.strip(" .!?,"):
            return
        if self.has_pending_approval():
            intent = resolve_intent(text, self.context)
            if intent.intent_type in ("hitl_approve", "hitl_reject", "cancel"):
                approved = (intent.intent_type == "hitl_approve")
                self.resolve_latest_approval(approved)
                return
        if self.live:
            self.refresh_page_context()
        # Keep the speaker's casing: notes, file text and names are data.
        normalized = re.sub(r"\s+dot\s+(com|org|net)\b", r".\1", text, flags=re.I)
        normalized = re.sub(r"\s+\.", ".", normalized)
        if normalized.strip():
            # A completed utterance has one plan. Validation happens before the
            # local model is asked to accept its individual steps.
            self.submit_decision(normalized)

    def request(self, request):
        command = request.get("command")
        if command == "listen": self.listen()
        elif command == "stop": self.stop()
        elif command == "finish": self.finish_recording()
        elif command == "text":
            if self.listening or self.voice is not None: self.stop()
            self.transcript(str(request.get("text", ""))[:4000], True)
        elif command in ("approve", "reject"):
            approval_id = request.get("id") or request.get("approval_id")
            approved = (command == "approve")
            self.resolve_approval(approval_id, approved)
        elif command == "save_note" and self.note and request.get("id") == self.note["id"]:
            self.note.update(title=str(request.get("title", "Untitled"))[:500], body=str(request.get("body", ""))[:100000])
            self.publish_note(show=False)
        elif command == "theme":
            self.themes.select(str(request.get("name", "")))
            self.emit(type="theme", theme=self.themes.current())
        elif command == "voice":
            mode = str(request.get("mode", ""))
            if mode not in ("elevenlabs", "kokoro", "local", "off"):
                raise ValueError("Choose the kokoro, elevenlabs, local or off voice")
            settings = json.loads((DATA / 'settings.json').read_text()) if (DATA / 'settings.json').exists() else {}
            settings["voice"] = mode
            (DATA / 'settings.json').write_text(json.dumps(settings, indent=2) + "\n")
            self.emit(type="action", message=f"Voice: {self.speaker.mode()}")
        elif command == "save_routine":
            from blok.routines import save_routine_dict
            try:
                routine = save_routine_dict(request.get("routine", {}), DATA)
                self.emit(type="routine_saved", routine=routine.to_dict())
            except Exception as error:
                self.emit(type="action", error=True, message=f"Failed to save routine: {error}")
        elif command == "list_routines":
            from blok.routines import list_routines
            routines = list_routines(DATA)
            self.emit(type="routines", routines=[r.to_dict() for r in routines.values()])
        elif command == "feedback":
            self.emit(type="action", message=str(request.get("message", "")))
        elif command == "diagnostics":
            self.emit(type="diagnostics", **get_diagnostics_summary())

    def main(self):
        self.speaker.enabled = True
        self.speaker.warm_up()
        self.live = True
        if os.environ.get('BLOK_STT') != 'voxtype':
            from blok import speech
            speech.warm_up()
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
                    elif event["type"] == "understood":
                        self.emit(type="understood", text=event["text"], model=event["model"])
                        self.emit(type="activity", state="thinking", message=f"Understood: “{event['text']}” · Laya is checking…")
                    elif event["type"] == "speech_busy":
                        self.listening = False
                        self.status("processing", "Transcribing locally…")
                        self.emit(type="activity", state="transcribing", message="Whisper is transcribing locally…")
                    elif event["type"] == "speech_text":
                        self.voice = None
                        self.listening = False
                        self.status("ready", "Microphone off")
                        self.emit(type="activity", state="idle")
                        if event["text"]:
                            self.transcript(event["text"], True)
                        else:
                            self.emit(type="action", error=True, message="I didn't catch that. Hold Ctrl+. and try again.")
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
