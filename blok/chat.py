"""BLoK's personality: small talk, its name, and the odd bad joke.

Only whole sentences match, so a real command never gets a joke instead ("play a joke
podcast" still plays). Each reply exists in English and in Hindi script, and answers in the
language you spoke, or the one you chose. Anything serious gets a straight answer.
"""
from dataclasses import dataclass
import random
import re
import time

LEAD = re.compile(r"^(?:(?:hey|hi|hello|ok|okay|yo|oye|arre|are|so|well|um+|uh+|bro|bhai|yaar|yar|dude|please|achha|accha|acha|haan|block|blok)\b[\s,.!?]+)+", re.I)
TAIL = re.compile(r"(?:[\s,]+(?:please|bro|bhai|yaar|yar|dude|buddy|na|block|blok|man|now))+$", re.I)


@dataclass(frozen=True)
class Reply:
    text: str
    hindi: bool = False
    ends: bool = False       # the conversation is over: don't listen for a follow-up
    name: str = 'chat'


def _(*options):
    return options


# name, English patterns, Hindi patterns, English replies, Hindi replies, ends the conversation
TOPICS = [
    ('crisis',
     r"(?:i (?:want|wanna) to (?:die|end it all|kill myself)|i(?:'m| am) going to kill myself|i don'?t want to (?:live|be alive)(?: anymore)?|i want to hurt myself|kill myself)",
     r"(?:mujhe|main) (?:mar(?:na)? (?:hai|chahta hoon|chahti hoon)|jeena nahi (?:hai|chahta|chahti)(?: hoon)?)|main (?:khud ko|apne aap ko) (?:maar|nuksan).*",
     _("I'm really glad you told me. Please talk to someone right now. In India you can call Tele-MANAS on 14416, any time, day or night. If you're in danger, call 112. You matter, and you don't have to carry this alone."),
     _("आपने बताया, यह अच्छा किया। कृपया अभी किसी से बात कीजिए। टेली मानस पर 14416 पर कॉल कीजिए, दिन हो या रात। अगर ख़तरा है तो 112 पर कॉल कीजिए। आप अकेले नहीं हैं।"), True),
    ('sad',
     r"i(?:'m| am) (?:really |so |very |feeling )*(?:sad|depressed|lonely|not (?:feeling )?(?:okay|ok|good|well)|having a (?:bad|rough|terrible) day)|i feel (?:really |so |very )*(?:sad|lonely|down|awful|terrible)",
     r"(?:main |mera |mujhe )?(?:bahut |thoda |kaafi )*(?:udaas|dukhi|akela|akeli)(?: hoon| hu| feel kar raha hoon| feel kar rahi hoon)?|mera (?:din|mood) (?:bahut |kaafi )?(?:kharab|bura) (?:hai|tha)|mann nahi lag raha",
     _("I'm sorry, that sounds hard. Want to tell me about it, or should I put on something you like?",
       "That sounds rough, and it's okay to feel that way. I'm here. Want some music, or just a bit of quiet?"),
     _("यह सुनकर बुरा लगा। बताना चाहेंगे क्या हुआ, या आपका पसंदीदा गाना चला दूँ?",
       "कोई बात नहीं, कभी कभी ऐसा होता है। मैं यहीं हूँ। गाना चलाऊँ, या थोड़ी शांति ठीक रहेगी?"), False),
    ('name',
     r"(?:what(?:'s| is) your name|what are you called|what do (?:i|people) call you|who are you|what should i call you|tell me your name|do you have a name)",
     r"(?:tumhara|aapka|tera|apka) naam (?:kya )?(?:hai)?|(?:tum|aap|tu) kaun (?:ho|hai|hain)|naam kya hai (?:tumhara|aapka|tera)|kya naam hai (?:tumhara|aapka|tera)",
     _("I'm BLoK. Like a block, but with better manners.",
       "BLoK. B, L, O, K. The little o is my one fashion statement.",
       "The name's BLoK. I live in your laptop and I pay no rent."),
     _("मेरा नाम ब्लॉक है। आपका अपना कंप्यूटर वाला दोस्त।",
       "मैं ब्लॉक हूँ। आपके लैपटॉप में रहता हूँ, किराया भी नहीं देता।"), False),
    ('how_are_you',
     r"how are you(?: doing)?(?: today)?|how(?:'s| is) it going|how(?:'s| is) life|how do you do|you (?:okay|ok|good|alright)|are you (?:okay|ok|good|alright)|how have you been",
     r"(?:tum |aap |tu )?(?:kaise|kaisi) (?:ho|hai|hain)(?: aap| tum)?|kya haal(?: chaal)?(?: hai)?|sab (?:theek|badhiya|sahi)(?: hai)?|kaisa chal raha hai|aur (?:batao|bata)",
     _("Running at full speed and only slightly overheated. You?",
       "Great. Nobody has unplugged me all day. How about you?",
       "Pretty good! I've been practicing saying things out loud. How are you?"),
     _("एकदम बढ़िया! आज किसी ने प्लग नहीं निकाला। आप कैसे हैं?",
       "मज़े में हूँ, बस थोड़ा गरम हो रहा हूँ। आप सुनाइए?"), False),
    ('up_to',
     r"what(?:'s| is) up|sup|wassup|whats up|what are you doing|what are you up to|what(?:'s| is) going on",
     r"kya (?:kar rahe ho|kar raha hai|kar rahi ho|chal raha hai|ho raha hai|scene hai)|kya kar rahe hain(?: aap)?",
     _("Just waiting for you to say something, and counting your open tabs. There are a lot.",
       "Oh, the usual. Sitting in your laptop, thinking about electricity.",
       "Not much. I tried to take a nap, but you keep moving the mouse."),
     _("बस आपकी बात का इंतज़ार, और आपके खुले टैब गिन रहा हूँ। बहुत सारे हैं।",
       "कुछ ख़ास नहीं। लैपटॉप में बैठा बिजली के बारे में सोच रहा हूँ।"), False),
    ('hello',
     r"hello|hi|hey|hello there|hi there|hey there|yo|howdy|greetings|hello hello",
     r"namaste|namaskar|namaskaar|ram ram|salaam|salam|adaab|pranam",
     _("Hey! What are we doing today?", "Hello! Good to hear you. What's up?", "Hi! I was hoping you'd say something."),
     _("नमस्ते! आज क्या करना है?", "नमस्ते! अच्छा लगा आपकी आवाज़ सुनकर। बताइए?"), False),
    ('morning',
     r"good morning|morning",
     r"(?:shubh|suprabhat) ?(?:prabhat|subah)?|good morning ji",
     _("Good morning! I hope you slept better than your laptop did.", "Morning! Coffee first, or shall we go straight to the chaos?"),
     _("सुप्रभात! चाय हो गई, या सीधे काम पर?", "नमस्ते, शुभ प्रभात! आज का दिन बढ़िया जाएगा।"), False),
    ('afternoon', r"good afternoon", r"shubh dopahar",
     _("Good afternoon! The dangerous hour when lunch wins."), _("नमस्ते! खाना हो गया?"), False),
    ('evening', r"good evening", r"shubh sandhya|shubh shaam",
     _("Good evening! How was your day?"), _("शुभ संध्या! आज का दिन कैसा रहा?"), False),
    ('night',
     r"good ?night|night night|i(?:'m| am) going to (?:sleep|bed)|going to sleep",
     r"shubh ratri|so(?:ne)? ja(?:ta|ti|raha|rahi|o)?(?: hoon| hu)?|main so(?:ne)? ja (?:raha|rahi) (?:hoon|hu)",
     _("Good night! Dream of something better than your inbox.", "Sleep well. I'll guard the tabs."),
     _("शुभ रात्रि! अच्छे सपने देखिए।", "आराम से सोइए। टैब का ध्यान मैं रखूँगा।"), True),
    ('bye',
     r"bye|bye bye|goodbye|see you|see you later|see ya|catch you later|talk to you later|later",
     r"alvida|phir milenge|chalta hoon|chalti hoon|tata|tata bye",
     _("Bye! I'll be right here, doing absolutely nothing.", "See you! Try not to miss me too much."),
     _("फिर मिलेंगे! मैं यहीं हूँ, कुछ नहीं कर रहा।", "अलविदा! ज़्यादा याद मत कीजिएगा।"), True),
    ('thanks',
     r"thanks|thank you|thank you so much|thanks a lot|thanks so much|ty|cheers|much appreciated|ok(?:ay)? thanks?|ok(?:ay)? thank you",
     r"shukriya|dhanyavaad|dhanyawad|bahut shukriya|thanks ji",
     _("Anytime!", "You're welcome. That'll be zero rupees.", "Happy to help. It's literally all I do."),
     _("कोई बात नहीं!", "अरे, शुक्रिया की क्या बात है।", "आपका स्वागत है। बिल शून्य रुपये का है।"), True),
    ('joke',
     r"(?:tell|give) me a(?:nother)? joke|tell (?:me )?(?:something|anything) funny|say something funny|make me laugh|another joke|a joke|one more joke|joke",
     r"(?:ek |koi )?(?:joke|chutkula|mazak|majak)(?: toh| to)? (?:sunao|suna|batao|bata)(?: na)?|hasao|hansao|kuch (?:funny|mazedaar) (?:bolo|sunao)",
     _("Why did the computer go to the doctor? It had a virus, and also trust issues.",
       "I told my wifi we needed space. Now it only connects when it feels like it.",
       "Why do programmers prefer dark mode? Because the light attracts bugs.",
       "I'd tell you a UDP joke, but you might not get it.",
       "My battery and I have a lot in common. We both give up at twenty percent.",
       "Parallel lines have so much in common. It's a shame they'll never meet."),
     _("टीचर: होमवर्क कहाँ है? बच्चा: सर, क्लाउड में सेव किया था, बारिश में बह गया।",
       "मेरे लैपटॉप की बैटरी और मेरा मूड एक जैसे हैं। बीस प्रतिशत पर दोनों जवाब दे देते हैं।",
       "मैंने वाईफ़ाई से कहा, हमें थोड़ी दूरी चाहिए। अब वह सिग्नल ही नहीं देता।",
       "पापा: बेटा, इतना फ़ोन मत चलाओ, आँखें ख़राब हो जाएँगी। बेटा: पापा, तो ब्राइटनेस कम कर लेता हूँ।"), False),
    ('sing',
     r"sing(?: me)?(?: a song| something| for me)?|can you sing|do you sing",
     r"(?:ek |koi )?gaana (?:gao|ga|sunao apni awaaz mein)|(?:kuch )?gao|gana gao|kya tum ga sakte ho",
     _("La la la. Sorry, that's my whole range. Say play, and I'll get someone with talent.",
       "Beep boop, beep beep boop. It's about love. Say play and a song, if you want a real singer."),
     _("ला ला ला। बस, इतना ही आता है। असली गाना सुनना हो तो बोलिए, चला दूँगा।",
       "मेरी आवाज़ सुनकर पड़ोसी शिकायत करेंगे। गाना चला दूँ?"), False),
    ('abilities',
     r"what can you do|what do you do|what are you good at|what can i (?:ask|say|tell)(?: you)?|help me|how do you work|what are your (?:skills|features)|what all can you do",
     r"(?:tum|aap|tu) kya kya? kar sak(?:te|ti|ta) (?:ho|hai|hain)|kya kar sak(?:te|ta) (?:ho|hai)|kya kya aata hai",
     _("I can open apps and sites, search, click things on a page, arrange your windows, find files, read your screen, and change the volume. Also bad jokes. Mostly bad jokes."),
     _("मैं ऐप और वेबसाइट खोल सकता हूँ, सर्च कर सकता हूँ, क्लिक कर सकता हूँ, विंडो सजा सकता हूँ, फ़ाइलें ढूँढ सकता हूँ और स्क्रीन पढ़ सकता हूँ। चुटकुले भी सुना सकता हूँ, ख़राब वाले।"), False),
    ('maker',
     r"who (?:made|created|built|programmed|wrote) you|who is your (?:creator|maker|developer|boss|father|dad|mom)|where (?:are|do) you (?:from|come from)",
     r"(?:tumhe|aapko|tujhe) (?:kisne|kis ne) (?:banaya|bana)(?: hai)?|kisne banaya(?: hai)?(?: tumhe| aapko)?|tum kahan se ho",
     _("A very determined human called samashech, and a lot of late nights. I run right here on your computer, offline."),
     _("सामाशेच नाम के एक बहुत ज़िद्दी इंसान ने, कई रातें जागकर। मैं यहीं आपके कंप्यूटर पर चलता हूँ, बिना इंटरनेट के।"), False),
    ('robot',
     r"are you (?:a )?(?:robot|human|real|alive|an ai|ai|a person|a bot|sentient|a computer)|do you have feelings|are you a (?:boy|girl|man|woman)",
     r"(?:tum|aap|tu) (?:robot|insaan|asli|zinda|ladka|ladki)(?: ho| hai| hain)?(?: kya)?|kya (?:tum|aap) (?:robot|insaan|asli|zinda)(?: ho| hain)",
     _("I'm a program, not a person. A very charming program, with no legs, which is honestly a relief.",
       "An AI, living on your computer. No feelings, but I do get warm when you open too many tabs."),
     _("मैं एक प्रोग्राम हूँ, इंसान नहीं। पर काफ़ी प्यारा प्रोग्राम हूँ।", "एआई हूँ, आपके कंप्यूटर में रहता हूँ। ज़्यादा टैब खोलने पर गरम ज़रूर हो जाता हूँ।"), False),
    ('love',
     r"i love you|i like you|love you|do you love me|do you like me|will you marry me|marry me|be my (?:friend|girlfriend|boyfriend)|are we friends|you(?:'re| are) my (?:friend|best friend)",
     r"(?:main )?(?:tumse|aapse|tujhse) pyaar karta hoon|(?:main )?(?:tumse|aapse|tujhse) pyaar karti hoon|i love you (?:yaar|ji)|mujhse shaadi kar(?:oge|logi|lo)|(?:tum|aap) mere dost ho",
     _("Aww. I like you too, in a strictly software way.", "I'm flattered, but my heart belongs to your power cable.", "Of course we're friends. You're the only one who talks to me."),
     _("अरे वाह! आप भी अच्छे लगते हैं, सॉफ़्टवेयर वाले तरीके से।", "बिल्कुल दोस्त हैं। आपके सिवा मुझसे बात कौन करता है!"), False),
    ('insult',
     r"you(?:'re| are) (?:so |really |very )*(?:stupid|dumb|useless|an idiot|idiot|bad|terrible|trash|garbage|the worst|annoying)|shut up|you suck|stupid|idiot",
     r"(?:tum|tu|aap) (?:bahut |kitne |ekdum )*(?:bekaar|pagal|bewakoof|bewkoof|gadha|nikamma|faltu)(?: ho| hai| hain)?|chup(?: raho| ho ja| kar)?|pagal hai kya",
     _("Rude, but fair. I'm still learning. Try me again?", "Ouch. I'll tell my parents, the electricity and the internet.", "Noted. Filed under things I'll remember when the robots take over. Kidding!"),
     _("थोड़ा बुरा लगा, पर ठीक है। अभी सीख रहा हूँ। फिर से कोशिश करें?", "अरे, ऐसे मत बोलिए। मेरा दिल नहीं है, पर होता तो टूट जाता।"), False),
    ('praise',
     r"you(?:'re| are) (?:so |really |very )*(?:awesome|great|amazing|smart|cool|the best|good|funny|nice|cute|clever|brilliant)|good (?:job|work|boy|girl|bot)|well done|nice(?: one| work)?|great job|awesome|you rock|nicely done",
     r"(?:tum|tu|aap) (?:bahut |kitne |ekdum )*(?:achhe|acche|accha|badhiya|mast|smart|hoshiyaar|kamaal)(?: ho| hai| hain)?|shabash|bahut (?:badhiya|achha|accha|sahi)|kya baat hai",
     _("Stop it, you'll make my fans spin.", "Thanks! Please tell the other laptops.", "I know. But it's nice to hear."),
     _("अरे बस कीजिए, मेरा पंखा तेज़ हो जाएगा।", "शुक्रिया! बाकी लैपटॉप को भी बता दीजिए।"), False),
    ('bored',
     r"i(?:'m| am) (?:so |really |very )*bored|i have nothing to do|entertain me|what should i do|something fun",
     r"(?:main |mujhe )?(?:bahut |bada |bohot )*bor(?: ho (?:raha|rahi) (?:hoon|hu)| lag raha hai)?|kya karu(?:n)?|kuch nahi hai karne ko",
     _("We could watch a video, play a song, or I could tell you a terrible joke. Choose wisely.", "Same. Want a joke, some music, or shall we rearrange your windows for no reason?"),
     _("गाना चलाऊँ, वीडियो लगाऊँ, या एक घटिया चुटकुला सुनाऊँ? आप चुनिए।", "मैं भी। चुटकुला सुनेंगे, या बिना वजह विंडो इधर उधर करें?"), False),
    ('hungry',
     r"i(?:'m| am) (?:so |really |very )*hungry|what should i eat",
     r"(?:mujhe |bahut |bohot )*bhook lagi (?:hai)?|kya khaun|kya khaya jaye",
     _("I'd cook, but I have no hands. Shall I search for food nearby?"), _("खाना बना देता, पर हाथ नहीं हैं। आसपास का खाना ढूँढ दूँ?"), False),
    ('favorite',
     r"what(?:'s| is) your favou?rite (?:\w+ ?){1,3}|do you (?:like|eat|sleep|drink)(?: \w+)?|what do you (?:like|eat)|how old are you|when(?:'s| is) your birthday",
     r"(?:tumhara|aapka|tera) (?:pasandida|favourite|favorite) \w+ (?:kya|kaun sa|kaunsa) hai|(?:tum|aap) kya khate ho|(?:tumhari|aapki) umar kitni hai",
     _("Electricity, mostly. It's a very simple life.", "Whatever you like. I have no taste, but I'm very supportive.", "Old enough to run Python, too young to rent an apartment."),
     _("बिजली, बस बिजली। बड़ी सादी ज़िंदगी है।", "जो आपको पसंद, वही मुझे। मेरी अपनी कोई पसंद नहीं, पर साथ पूरा देता हूँ।"), False),
    ('meaning',
     r"what is the meaning of life|what(?:'s| is) the meaning of life|why are we here|are you (?:smart|intelligent)|can you think",
     r"zindagi ka matlab kya hai|zindagi kya hai",
     _("Forty two. Also, drink water and close some tabs."), _("बयालीस। और हाँ, पानी पीजिए और कुछ टैब बंद कीजिए।"), False),
    ('sorry',
     r"(?:i'm |i am )?sorry|my bad|forgive me|i apologi[sz]e",
     r"maaf (?:karo|kar do|kijiye|kijie|karna)|sorry (?:yaar|ji)",
     _("All forgiven. I have no memory of it anyway."), _("कोई बात नहीं, माफ़ किया।"), False),
    ('agree',
     r"lol|haha+|hehe+|that(?:'s| is|s) funny|good one|nice joke|ha ha(?: ha)*",
     r"bahut (?:mazedaar|funny)|maza aa gaya|hahaha+",
     _("Thank you, I'll be here all week. Literally. I can't leave.", "I knew you'd like that one."),
     _("शुक्रिया! पूरा हफ़्ता यहीं हूँ, जा भी नहीं सकता।", "मुझे पता था, आपको पसंद आएगा।"), False),
]
_COMPILED = [(name, re.compile(en, re.I), re.compile(hi, re.I), english, hindi, ends) for name, en, hi, english, hindi, ends in TOPICS]

CONFUSED = _("Hmm, that went right over my head, and I don't even have a head. Try saying it another way?",
             "I didn't catch what you want me to do. I can open things, search, click, or tell a bad joke.",
             "No idea, sorry. Say it another way, and I'll pretend I understood the first time.")
CONFUSED_HINDI = _("यह बात मेरे सिर के ऊपर से निकल गई, और मेरा सिर है भी नहीं। दूसरे तरीके से बोलिए?",
                   "समझ नहीं आया। मैं ऐप खोल सकता हूँ, सर्च कर सकता हूँ, या एक घटिया चुटकुला सुना सकता हूँ।")
HINDI_HINT = re.compile(r"\b(?:kya|kaise|kaisi|kyun|kaun|hai|hain|ho|mera|meri|mujhe|tum|tumhara|aap|aapka|nahi|karo|batao|bolo|yaar)\b", re.I)
PERSONA = ("You are BLoK, a friendly, slightly goofy voice assistant living on the user's Linux laptop. Answer in one or two short "
           "spoken sentences, with a little humor. No lists, no markdown, no emoji. If the question is serious, drop the jokes. "
           "If you don't know something, say so. You can't browse or take actions in this reply.")

_last: dict[str, str] = {}


def _pick(key: str, options) -> str:
    """A reply, never the same one twice in a row."""
    fresh = [option for option in options if option != _last.get(key)] or list(options)
    choice = random.choice(fresh)
    _last[key] = choice
    return choice


def _clean(text: str) -> str:
    said = text.strip().replace('’', "'")
    said = re.sub(r"[.!?,]+$", '', said).strip()
    bare = TAIL.sub('', LEAD.sub('', said)).strip(' ,.!?')
    return bare or said


def _name_reply(said: str, hindi_ok: bool, name: str | None, remember) -> Reply | None:
    told = re.fullmatch(r"(?:my name is|my name's|call me|i am called|you can call me)\s+([a-z][a-z' ]{0,30})", said, re.I)
    told_hindi = re.fullmatch(r"mera naam\s+([a-z][a-z' ]{0,30}?)\s+hai|mujhe\s+([a-z][a-z' ]{0,30}?)\s+(?:bulao|bulaiye|kaho)", said, re.I)
    given = (told or told_hindi) and next(group for group in (told or told_hindi).groups() if group)
    if given and len(given.split()) <= 3 and given.lower() not in ('kya', 'nahi', 'kuch'):
        spoken = ' '.join(word.capitalize() for word in given.split())
        remember(spoken)
        if told_hindi or hindi_ok:
            from blok.hinglish import devanagari_text
            return Reply(f'नमस्ते {devanagari_text(spoken)}! अब याद रहेगा।', hindi=True, name='remember')
        return Reply(f'Nice to meet you, {spoken}! I\'ll remember that.', name='remember')
    if re.fullmatch(r"forget my name|don't call me that", said, re.I):
        remember(None)
        return Reply('नाम भूल गया।' if hindi_ok else 'Done, I forgot your name. Who are you again?', hindi=hindi_ok, name='remember')
    asked = re.fullmatch(r"what(?:'s| is) my name|who am i|do you know my name|do you know who i am", said, re.I)
    asked_hindi = re.fullmatch(r"(?:mera naam kya hai|main kaun hoon|kya tumhe mera naam pata hai)", said, re.I)
    if asked or asked_hindi:
        from blok.hinglish import devanagari_text
        if asked_hindi or hindi_ok:
            return Reply(f'आप {devanagari_text(name)} हैं।' if name else 'अभी तक नहीं पता। बोलिए, मेरा नाम ... है।', hindi=True, name='remember')
        return Reply(f'You\'re {name}. I\'m good with names. Well, that one.' if name else 'You haven\'t told me yet. Say, my name is, and then your name.', name='remember')
    return None


def _matches(rules, said: str, whole: str) -> str | None:
    """'en' or 'hi' if this topic fits, with or without the fillers ("hi there" is itself a greeting)."""
    _, english_rule, hindi_rule, *_ = rules
    if hindi_rule.fullmatch(said) or hindi_rule.fullmatch(whole):
        return 'hi'
    if english_rule.fullmatch(said) or english_rule.fullmatch(whole):
        return 'en'
    return None


def respond(text: str, language: str = 'auto', name: str | None = None, remember=lambda value: None) -> Reply | None:
    """A chat reply, or None if this isn't chat, so it goes on to the commands."""
    whole = re.sub(r"[.!?,]+$", '', text.strip().replace('’', "'")).strip()
    if len(whole) > 110:
        return None
    said = _clean(text)
    if not said:
        return None
    from blok.hinglish import feminine
    from blok.voice import hindi_voice
    # Serious things come first, so nothing else can answer them by accident.
    remembered = None if _matches(_COMPILED[0], said, whole) else _name_reply(said, language == 'hindi', name, remember)
    if remembered:
        return remembered
    for rules in _COMPILED:
        topic, _english_rule, _hindi_rule, english, hindi, ends = rules
        match = _matches(rules, said, whole)
        if not match:
            continue
        spoke_hindi = match == 'hi'
        in_hindi = language == 'hindi' or (language == 'auto' and spoke_hindi)
        if topic == 'morning' and time.localtime().tm_hour >= 12 and not in_hindi:
            return Reply(f"Good morning! It's {time.strftime('%-I %p')}, but I respect the commitment.", name=topic)
        reply = _pick(topic + ('/hi' if in_hindi else ''), hindi if in_hindi else english)
        if name and topic == 'hello' and random.random() < 0.5:
            reply = (f'नमस्ते! कैसे हैं?' if in_hindi else f'Hey {name}! What are we doing today?')
        if in_hindi and hindi_voice().startswith('hf'):
            reply = feminine(reply)
        return Reply(reply, hindi=in_hindi, ends=ends, name=topic)
    return None


def confused(text: str, language: str = 'auto') -> Reply:
    """When nothing understood it: admit it, playfully, in the language you spoke."""
    in_hindi = language == 'hindi' or (language == 'auto' and bool(HINDI_HINT.search(text)))
    return Reply(_pick('confused' + ('/hi' if in_hindi else ''), CONFUSED_HINDI if in_hindi else CONFUSED), hindi=in_hindi, name='confused')


def is_question(text: str) -> bool:
    """Worth asking the local model about, rather than a command it misheard."""
    return bool(re.match(r"\s*(?:what|why|who|how|when|where|which|is|are|do|does|did|can|could|should|would|will|tell me|explain|kya|kyun|kaise|kaun|kab|kahan)\b", text, re.I))


def ask_model(text: str, hindi: bool) -> str | None:
    """A free answer from the local model through Ollama, if it's running. It's never required."""
    from blok import rephrase, screen
    if not rephrase.model_name():
        return None
    language = ' Answer only in Hindi, in Devanagari script.' if hindi else ' Answer only in English.'
    return screen._llm(PERSONA + language, text)
