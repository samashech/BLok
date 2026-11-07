"""BLoK watches you play, comments, and remembers what happened. It never touches the game.

Right now that means slither.io, which shows your length, rank and the leaderboard as plain
page text, so BLoK reads exact numbers about once a second through the browser extension.
Nothing is sent to the game and no input is made. Everything that happens goes into a local
timeline (data/games/slither.jsonl), so you can ask about it later, even after a restart.
"""
from dataclasses import dataclass, field
import json
import random
import re
import time

LENGTH_MARKS = (100, 250, 500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 30000)
RANK_MARKS = (100, 50, 25, 10, 5, 3, 2, 1)
BIG_JUMP = 0.25         # gaining this share in a few seconds means you ate something big
BIG_JUMP_MIN = 60
QUIET_SECONDS = 7       # at least this long between remarks, unless it's important
BANTER_SECONDS = 50     # say something if nothing has happened for this long


def is_game_page(url: str) -> bool:
    return bool(re.match(r'https?://(?:www\.)?slither\.io(?:[/?#]|$)', url or ''))


def read_state(text: str) -> dict:
    """What the page says right now. Page text is only searched for numbers, never obeyed."""
    text = (text or '').replace('\xa0', ' ')
    state = {'playing': False, 'length': None, 'rank': None, 'players': None, 'final': None, 'top': None}
    length = re.search(r'Your length:\s*([\d,]+)', text)
    rank = re.search(r'Your rank:\s*([\d,]+)\s*of\s*([\d,]+)', text)
    final = re.search(r'final length (?:was\s*)?([\d,]+)', text, re.I)
    if length:
        state['playing'] = True
        state['length'] = int(length[1].replace(',', ''))
    if rank:
        state['rank'], state['players'] = int(rank[1].replace(',', '')), int(rank[2].replace(',', ''))
    if final:
        state['final'] = int(final[1].replace(',', ''))
    board = re.search(r'Leaderboard\s*\n+((?:\s*[\d,]+\s*\n)+)', text)
    if board:
        scores = [int(n.replace(',', '')) for n in re.findall(r'[\d,]+', board[1])]
        state['top'] = scores[0] if scores else None
    return state


@dataclass
class Event:
    kind: str
    at: float
    data: dict = field(default_factory=dict)
    important: bool = False


class Session:
    """Turns readings into things that happened. Doesn't speak, read pages or know the time by itself."""

    def __init__(self, best: int = 0, now: float = 0.0):
        self.best_before = best
        self.best = best
        self.started = now
        self.lives: list[dict] = []
        self.life = None
        self.previous = None        # last length, a few readings back, for sudden jumps
        self.recent: list[tuple[float, int]] = []
        self.new_best_said = False

    def feed(self, state: dict, now: float) -> list[Event]:
        if state.get('playing') and state.get('length') is not None:
            return self._playing(state, now)
        if self.life:
            return self._died(state, now)
        return []

    def _playing(self, state, now):
        events = []
        length, rank = state['length'], state.get('rank')
        if not self.life:
            self.life = {'started': now, 'length': length, 'peak': length, 'rank': rank, 'best_rank': rank, 'marks': set(), 'ranks': set(), 'players': state.get('players')}
            self.recent = []
            self.new_best_said = False
            events.append(Event('life_start', now, {'number': len(self.lives) + 1, 'best': self.best}))
        life = self.life
        life['players'] = state.get('players') or life['players']
        self.recent = [(t, n) for t, n in self.recent if now - t <= 6] + [(now, length)]
        low = min(n for _, n in self.recent)
        gained = length - low
        if gained >= BIG_JUMP_MIN and gained >= low * BIG_JUMP:
            events.append(Event('big_jump', now, {'gained': gained, 'length': length}))
            self.recent = [(now, length)]
        if length < life['length'] * 0.8 and life['length'] - length >= 50:
            events.append(Event('shrank', now, {'lost': life['length'] - length, 'length': length}))
        for mark in LENGTH_MARKS:
            if length >= mark and mark not in life['marks']:
                life['marks'].add(mark)
                if life['started'] != now:         # joining at a size isn't reaching it
                    events.append(Event('length_mark', now, {'mark': mark, 'length': length}, important=mark >= 1000))
        if length > self.best:
            if self.best_before and not self.new_best_said and length > self.best_before:
                self.new_best_said = True
                events.append(Event('new_best', now, {'length': length, 'old': self.best_before}, important=True))
            self.best = length
        if rank is not None:
            for mark in RANK_MARKS:
                if rank <= mark and mark not in life['ranks']:
                    life['ranks'].add(mark)
                    if life['started'] != now:
                        events.append(Event('rank_mark', now, {'mark': mark, 'rank': rank, 'players': state.get('players')}, important=mark <= 10))
            if life['best_rank'] is None or rank < life['best_rank']:
                life['best_rank'] = rank
            life['rank'] = rank
        life['length'] = length
        life['peak'] = max(life['peak'], length)
        return events

    def _died(self, state, now):
        life, self.life = self.life, None
        final = state.get('final') or life['length']
        self.best = max(self.best, final)
        record = {'number': len(self.lives) + 1, 'final': final, 'peak': max(life['peak'], final), 'best_rank': life['best_rank'],
                  'seconds': round(now - life['started']), 'players': life['players']}
        self.lives.append(record)
        return [Event('death', now, {**record, 'best': self.best, 'was_best': final >= self.best and final > self.best_before}, important=True)]

    def summary(self) -> dict:
        lives = self.lives
        return {'lives': len(lives), 'best': max((l['peak'] for l in lives), default=self.life['peak'] if self.life else 0),
                'best_rank': min((l['best_rank'] for l in lives if l['best_rank']), default=self.life['best_rank'] if self.life else None),
                'seconds': sum(l['seconds'] for l in lives)}


def _(*options):
    return options


LINES = {
    'watching': (_('Okay {name}, I\'m watching. Commentary is on. Show me what this snake can do.', 'Commentary on! Eat well and try not to hit anyone.'),
                 _('ठीक है {name}, मैं देख रहा हूँ। कमेंट्री चालू है। दिखाइए इस साँप का दम।', 'कमेंट्री चालू! ख़ूब खाइए, और किसी से टकराइए मत।')),
    'waiting': (_('Commentary is on. Open slither dot io and hit play, I\'ll be watching.',), _('कमेंट्री चालू है। स्लिदर खोलकर प्ले दबाइए, मैं देख रहा हूँ।',)),
    'life_start': (_('And we\'re off! Tiny snake, big dreams.', 'Fresh snake, fresh start. Everyone out there is food.', 'Here we go again. This is the one, I can feel it.'),
                   _('शुरू! छोटा साँप, बड़े सपने।', 'नया साँप, नई शुरुआत। बाहर सब खाना है।', 'चलिए फिर से। इस बार पक्का।')),
    'big_jump': (_('Whoa, plus {gained}! Somebody just became dinner.', 'Huge meal! That\'s {gained} in one go.', 'Delicious. {gained} bigger, just like that.'),
                 _('अरे वाह, {gained} बढ़ गए! कोई तो खाना बन गया।', 'क्या दावत थी! एक बार में {gained}।')),
    'shrank': (_('Careful, that boost cost you {lost}.', 'You\'re burning length, down {lost}. Worth it, I hope.'), _('संभलकर, बूस्ट में {lost} कम हो गए।',)),
    'length_mark': (_('{mark} long! Look at you go.', 'That\'s {mark}. Now we\'re a real snake.', '{mark} and growing. People should start worrying.'),
                    _('{mark} लंबाई! क्या बात है।', '{mark} हो गए। अब असली साँप बने हैं।')),
    'new_best': (_('New personal best! You just passed {old}.', 'That\'s your record, {name}! Everything from here is history.'),
                 _('नया रिकॉर्ड! {old} पार कर लिया।', 'यह आपका सबसे अच्छा स्कोर है, {name}!')),
    'rank_mark': (_('Top {mark}! Rank {rank} out of {players}.', 'You just broke into the top {mark}.'), _('टॉप {mark} में आ गए! {players} में से {rank} नंबर।',)),
    'rank_one': (_('Number one on the whole server! Everybody bow to the snake.', 'You are number one, {name}! Do not look down.'), _('पूरे सर्वर पर नंबर एक! सब सलाम कीजिए।',)),
    'death': (_('Oh no! Down at {final}, after {duration}.', 'And that\'s it. {final} long, {duration}. A brave snake.', 'Ouch! {final}, and they\'re already eating you.'),
              _('अरे नहीं! {final} पर ख़त्म, {duration} में।', 'बस, यहीं तक। {final} लंबाई, {duration}। बहादुर साँप था।')),
    'death_best': (_('Gone, but what a run! {final} is your best yet.',), _('गए, पर क्या खेल था! {final} आपका अब तक का सबसे अच्छा।',)),
    'banter': (_('Nice and steady. Length is {length}, rank {rank}.', 'Snakes don\'t have hands, and yet here you are, using a mouse.', 'Still alive. I\'m as surprised as you are.',
                 'Quiet out there. Too quiet. Length {length}.', 'Rank {rank} of {players}. The leader has {top}, no pressure.'),
               _('आराम से चल रहा है। लंबाई {length}, रैंक {rank}।', 'अभी तक ज़िंदा हैं। मैं भी हैरान हूँ।', 'बड़ी शांति है। कुछ तो गड़बड़ है। लंबाई {length}।', '{players} में से {rank} नंबर। चलते रहिए।')),
    'muted': (_('Okay, zipping it. I\'m still keeping score.',), _('ठीक है, चुप। स्कोर मैं रखता रहूँगा।',)),
    'unmuted': (_('I\'m back! Did you miss me?',), _('मैं वापस आ गया! याद किया?',)),
    'not_watching': (_('I\'m not watching a game right now.',), _('अभी मैं कोई गेम नहीं देख रहा।',)),
    'no_memory': (_('I don\'t have any games to remember yet. Say start commentary when you play.',), _('अभी कोई गेम याद नहीं है। खेलते समय बोलिए, कमेंट्री शुरू करो।',)),
}
_last: dict[str, str] = {}


def say_duration(seconds: float, hindi: bool) -> str:
    seconds = int(seconds)
    minutes, rest = seconds // 60, seconds % 60
    if hindi:
        return (f'{minutes} मिनट' if minutes else f'{rest} सेकंड')
    if minutes:
        return f'{minutes} minute' + ('s' if minutes != 1 else '')
    return f'{rest} seconds'


def line(kind: str, hindi: bool, **values) -> str:
    """One remark, never the same one twice in a row. Lines missing a number are skipped."""
    options = [option for option in LINES[kind][1 if hindi else 0] if _fills(option, values)] or list(LINES[kind][1 if hindi else 0])
    fresh = [option for option in options if option != _last.get(kind)] or options
    choice = random.choice(fresh)
    _last[kind] = choice
    return _fill(choice, values)


def _fills(option: str, values: dict) -> bool:
    return all(values.get(key) is not None for key in re.findall(r'\{(\w+)\}', option) if key != 'name')


def _fill(option: str, values: dict) -> str:
    def value(found):
        key = found[1]
        if key == 'name':
            return values.get('name_hi' if re.search('[ऀ-ॿ]', option) else 'name') or ''
        return str(values.get(key, ''))
    filled = re.sub(r'\{(\w+)\}', value, option)
    filled = re.sub(r'\s+([,.!?।])', r'\1', re.sub(r'\s{2,}', ' ', filled))
    return re.sub(r',([.!?।])', r'\1', filled).strip()


def remark(event: Event, hindi: bool, name: str | None = None, name_hi: str | None = None) -> str:
    data = dict(event.data, name=name, name_hi=name_hi)
    if 'seconds' in data:
        data['duration'] = say_duration(data['seconds'], hindi)
    kind = event.kind
    if kind == 'rank_mark' and data.get('mark') == 1:
        kind = 'rank_one'
    if kind == 'death' and data.get('was_best'):
        kind = 'death_best'
    return line(kind, hindi, **data)


class Commentator:
    """Decides when to speak, so the game is watched closely but you aren't talked at."""

    def __init__(self, now: float = 0.0):
        self.last_said = now - QUIET_SECONDS
        self.last_event = now
        self.muted = False

    def choose(self, events: list[Event], now: float, busy: bool, state: dict | None = None) -> Event | None:
        if events:
            self.last_event = now
        if self.muted:
            return None
        important = next((e for e in events if e.important), None)
        if important:
            self.last_said = now
            return important        # worth interrupting
        if busy or now - self.last_said < QUIET_SECONDS:
            return None
        if events:
            self.last_said = now
            return events[0]
        if state and state.get('playing') and now - self.last_event >= BANTER_SECONDS and now - self.last_said >= BANTER_SECONDS:
            self.last_said = self.last_event = now
            return Event('banter', now, {k: state.get(k) for k in ('length', 'rank', 'players', 'top')})
        return None


class Memory:
    """Everything that happened, kept on this computer. Survives restarts."""

    def __init__(self, path):
        self.path = path

    def add(self, kind: str, data: dict | None = None, at: float | None = None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a') as out:
            out.write(json.dumps({'at': time.time() if at is None else at, 'kind': kind, **(data or {})}) + '\n')

    def all(self) -> list[dict]:
        try:
            lines = self.path.read_text().splitlines()
        except OSError:
            return []
        found = []
        for text in lines:
            try:
                found.append(json.loads(text))
            except ValueError:
                pass            # a line cut short by a crash shouldn't lose the rest
        return found

    def deaths(self) -> list[dict]:
        return [e for e in self.all() if e.get('kind') == 'death']

    def best(self) -> int:
        return max((e.get('peak', e.get('final', 0)) for e in self.deaths()), default=0)

    def last_session(self) -> list[dict]:
        """Events since the most recent start."""
        events = self.all()
        start = max((i for i, e in enumerate(events) if e.get('kind') == 'session_start'), default=0)
        return events[start:]


# What you can say. English and romanized Hindi; whole sentences only, like chat.
_FILLER = re.compile(r"^(?:(?:hey|ok|okay|so|please|bro|bhai|yaar|block|blok|arre|achha|accha)\b[\s,.!?]+)+|(?:[\s,]+(?:please|bro|bhai|yaar|na|block|blok))+$", re.I)
START = re.compile(r"(?:start|begin|turn on|do)(?: the| game| my)* commentary|commentary (?:on|start)|commentate(?: on)?(?: my| this| the)?(?: game| gameplay| match)?(?: for me)?|"
                   r"watch me play(?: slither)?|watch (?:my|this) game|game mode(?: on)?|let'?s play(?: slither)?|commentary (?:shuru|chalu|start) (?:karo|kar do|kar)|"
                   r"(?:mera |meri )?(?:game|khel) (?:dekho|dekh)|commentary karo", re.I)
STOP = re.compile(r"(?:stop|end|turn off|finish)(?: the| game| my)* commentary|commentary (?:off|stop)|stop watching(?: me| my game)?|game mode off|i(?:'m| am) done playing|game over|"
                  r"commentary (?:band|bandh|rok) (?:karo|kar do|kar)|(?:game|khel) (?:khatam|band)(?: karo| ho gaya)?", re.I)
MUTE = re.compile(r"(?:be )?quiet(?: for a (?:bit|while|minute))?|shut up|hush|stop talking|chup(?: raho| ho ja| ho jao| kar| karo)?|mat bolo|bolna band karo|silence", re.I)
UNMUTE = re.compile(r"(?:you can )?(?:talk|speak)(?: again)?|keep talking|commentate again|start talking|resume commentary|bolo|ab bolo|phir se bolo|bol sakte ho", re.I)
ASK_SUMMARY = re.compile(r"what happened|how (?:did|am|'?m) i (?:do|doing)|how(?:'s| is) (?:it|the game) going|how (?:was|did)(?: my| the)? (?:last )?game(?: go)?|(?:give me a |game )?summary|"
                         r"what happened (?:in|during)(?: my| the)?(?: last)? (?:game|match)|recap|(?:kya hua|kaisa chal raha hai|kaisa khel raha hoon|game kaisa raha|pichle game mein kya hua)", re.I)
ASK_BEST = re.compile(r"what(?:'s| is| was) my (?:best|high) ?(?:score|length|game)?(?: ever)?|what(?:'s| is) my record|my (?:high score|best score)|mera (?:best|record|sabse accha)(?: score)?(?: kya hai)?", re.I)
ASK_DEATHS = re.compile(r"how many (?:times )?(?:did|have) i (?:die|died)(?: so far)?|how many (?:deaths|lives|games)(?: so far)?|kitni baar (?:mara|mari|mar gaya|mar gayi)(?: hoon)?", re.I)
ASK_NOW = re.compile(r"what(?:'s| is) my (?:length|rank|score)|how (?:long|big) am i|where am i|meri? (?:length|rank|lambai)(?: kya| kitni)?(?: hai)?", re.I)
ASK_TIME = re.compile(r"how long have i been (?:playing|at this)|how much time(?: have i played)?|kitni der se khel raha hoon", re.I)
ASK_KILLER = re.compile(r"who (?:killed|ate|got) me|what killed me|kisne (?:maara|mara|khaya)", re.I)
_HINDI = re.compile(r"\b(?:kya|kaisa|kaise|karo|kar|mera|meri|kitni|kisne|chup|bolo|khel|dekho|hua|band|shuru|mat|khatam|raha|hoon|lambai)\b", re.I)


def understand(text: str) -> tuple[str | None, bool]:
    """(what you asked for, whether you said it in Hindi). None if it's not about the game."""
    said = _FILLER.sub('', re.sub(r"[.!?,]+$", '', text.strip().replace('’', "'"))).strip()
    for name, rule in (('start', START), ('stop', STOP), ('mute', MUTE), ('unmute', UNMUTE), ('summary', ASK_SUMMARY), ('best', ASK_BEST),
                       ('deaths', ASK_DEATHS), ('now', ASK_NOW), ('time', ASK_TIME), ('killer', ASK_KILLER)):
        if rule.fullmatch(said):
            return name, bool(_HINDI.search(said))
    return None, False


def answer_summary(memory: Memory, session: Session | None, hindi: bool) -> str:
    deaths = [e for e in memory.last_session() if e.get('kind') == 'death']
    alive = session.life if session else None
    if not deaths and not alive:
        return line('no_memory', hindi)
    parts = []
    if deaths:
        best = max(deaths, key=lambda d: d.get('peak', 0))
        total = sum(d.get('seconds', 0) for d in deaths)
        rank = min((d['best_rank'] for d in deaths if d.get('best_rank')), default=None)
        if hindi:
            parts.append(f'{len(deaths)} बार मरे, {say_duration(total, True)} खेले। सबसे लंबा {best.get("peak")}' + (f', सबसे अच्छी रैंक {rank}' if rank else '') + '।')
            parts.append(f'आख़िरी साँप {deaths[-1].get("final")} पर ख़त्म हुआ।')
        else:
            parts.append(f'{len(deaths)} ' + ('life' if len(deaths) == 1 else 'lives') + f' over {say_duration(total, False)}. Longest was {best.get("peak")}' + (f', best rank {rank}' if rank else '') + '.')
            parts.append(f'Your last snake ended at {deaths[-1].get("final")}.')
    if alive:
        parts.append(f'अभी लंबाई {alive["length"]}' + (f', रैंक {alive["rank"]}' if alive.get('rank') else '') + '।' if hindi
                     else f'Right now you\'re at {alive["length"]}' + (f', rank {alive["rank"]}' if alive.get('rank') else '') + '.')
    return ' '.join(parts)


def answer(kind: str, memory: Memory, session: Session | None, hindi: bool, now: float) -> str:
    """Answers come only from what was recorded. If it wasn't seen, it says so."""
    if kind == 'summary':
        return answer_summary(memory, session, hindi)
    if kind == 'best':
        best = max(memory.best(), session.best if session else 0)
        if not best:
            return line('no_memory', hindi)
        return f'आपका सबसे अच्छा {best} है।' if hindi else f'Your best ever is {best}.'
    if kind == 'deaths':
        count = len([e for e in memory.last_session() if e.get('kind') == 'death'])
        total = len(memory.deaths())
        if hindi:
            return f'इस बार {count} बार, और कुल {total} बार।'
        return f'{count} this session, {total} all time.' + (' Very brave.' if total > 5 else '')
    if kind == 'now':
        life = session.life if session else None
        if not life:
            return 'अभी आप खेल नहीं रहे।' if hindi else 'You\'re not in a game right now.'
        if hindi:
            return f'लंबाई {life["length"]}' + (f', रैंक {life["rank"]}' if life.get('rank') else '') + '।'
        return f'You\'re {life["length"]} long' + (f', rank {life["rank"]} of {life["players"]}' if life.get('rank') and life.get('players') else '') + '.'
    if kind == 'time':
        if not session:
            return line('not_watching', hindi)
        return f'{say_duration(now - session.started, True)} से खेल रहे हैं।' if hindi else f'About {say_duration(now - session.started, False)}.'
    if kind == 'killer':
        return 'यह मुझे नहीं दिखता। मैं सिर्फ़ स्कोर पढ़ता हूँ, किसने मारा यह नहीं पता चलता।' if hindi \
            else 'I can\'t see that. I only read the score, so I know you died, but not who did it.'
    return ''
