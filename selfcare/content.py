"""Gentle suggestions and prompts, so nobody has to start from a blank page."""

JOURNAL_PROMPTS = [
    ("today", "How was today, in a few words?"),
    ("drained", "What drained your energy today?"),
    ("lifted", "What lifted you, even a little?"),
    ("grateful", "Three small things you're grateful for"),
    ("worry", "What's on your mind that you'd like to set down?"),
    ("kind", "What would you say to a friend feeling the way you do?"),
    ("proud", "Something you handled well recently"),
    ("tomorrow", "One small thing you'd like to do tomorrow"),
]

SAFETY_STEPS = [
    {"key": "warning_signs", "title": "My warning signs", "help": "Thoughts, feelings or situations that tell me a hard time may be starting.",
     "suggestions": ["Not sleeping well", "Pulling away from people", "Feeling hopeless", "Can't stop crying", "Feeling numb",
                     "Racing thoughts", "Not eating", "Drinking more than usual"]},
    {"key": "coping", "title": "Things I can do on my own", "help": "Small things that help me feel even a little calmer.",
     "suggestions": ["Slow breathing", "Go for a walk", "Take a shower", "Listen to music", "Write in my journal",
                     "Pray or meditate", "Make a cup of tea", "Grounding exercise (5-4-3-2-1)"]},
    {"key": "distractions", "title": "People and places that take my mind off things", "help": "Where I can go or who I can be around.",
     "suggestions": ["A friend's house", "Church, mosque or temple", "The park", "A coffee shop", "Family", "The gym"]},
    {"key": "people", "title": "People I can ask for help", "help": "Someone I trust who I can call or message.", "suggestions": []},
    {"key": "professionals", "title": "Professionals I can contact", "help": "My counsellor, doctor or therapist, and their number.", "suggestions": []},
    {"key": "reasons", "title": "Reasons that matter to me", "help": "People, hopes and things worth holding on to.",
     "suggestions": ["My family", "My friends", "My pet", "My faith", "My future plans", "Finishing my studies", "People who love me"]},
]

RELATIONSHIPS = ["Partner", "Parent", "Sibling", "Friend", "Relative", "Colleague", "Neighbour", "Other"]
