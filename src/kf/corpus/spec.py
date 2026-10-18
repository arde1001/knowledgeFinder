"""Deterministic skeleton of the synthetic association.

Everything the tests rely on (users, drives, shares, which file holds which fact, which strings are fake PII)
is decided here from a seed. The LLM only writes filler prose around it (see generate.py).
"""

import random
import re
from dataclasses import dataclass, field
from datetime import date

from kf.perms import Policy

# The three kinds of people. Board reads every drive; a leader reads Leaders, Archive and the own committee's drive;
# a committee member reads only Members (plus whatever was shared with them).
ROLE_BOARD, ROLE_LEADER, ROLE_MEMBER = "test.board", "test.leader", "test.committee_member"
# drive id -> (display name, folder on disk, contact role, topic name in file titles, how the drive is described to the writer model)
# The folder has no colon (not allowed in Windows file names); the display name is what people see.
DRIVES = {
    "leaders": ("01_Leaders", "01_Leaders", "Leaders coordinator", "Leaders", "the association's committee and region leaders"),
    "archive": ("Archive", "Archive", "Archivist", "Archive", "the association's archive of past years"),
    "members": ("Members", "Members", "Secretary", "Association", "all members of the association"),
    "com_flc": ("Com: FLC", "Com_FLC", "FLC committee leader", "FLC committee", "the FLC committee"),
    "com_ac": ("Com: AC", "Com_AC", "AC committee leader", "AC committee", "the AC committee"),
    "board": ("Board", "Board", "Chairperson", "Board", "the board"),
}
ENTITIES = ("com_flc", "com_ac")  # committees with an own drive, readable by their leaders
BOARD_SIZE, LEADERS_PER_ENTITY, MEMBERS_PER_ENTITY = 3, 2, 6
ARCHIVE_YEARS = [2021, 2022, 2023]


EVENTS = ["Spring Gala", "Freshers Week", "Autumn Hackathon", "Winter Ball", "Career Fair", "Summer Picnic",
          "Charity Run", "Alumni Homecoming", "Culture Night", "Welcome Cruise", "Sports Day", "Open Mic Night"]
YEARS = [2024, 2025, 2026]
FIRST = ["Lukas", "Sofia", "Mateo", "Camille", "Pieter", "Elena", "Marco", "Ingrid", "Pierre", "Katarzyna", "Dimitris",
         "Aoife", "Luca", "Ana", "Tomas", "Eva", "Andrei", "Marta", "Henrik", "Clara", "Stefan", "Nora", "Joao", "Ilse",
         "Mihai", "Zofia", "Bruno", "Lena", "Matteo", "Greta", "Oskar", "Petra", "Rafael", "Ioana", "Niko"]
LAST = ["Novak", "Rossi", "Kowalski", "Dubois", "Garcia", "Jansen", "Muller", "Papadopoulos", "Silva", "Nilsson", "Horvat",
        "Popescu", "Murphy", "Fernandez", "Schmidt", "Andersen", "Kovacs", "Bianchi", "Dvorak", "Lindqvist", "Costa",
        "Moreau", "Wojcik", "Ivanov", "Conti", "Vos", "Maier", "Petrov", "Gallagher", "Santos", "Hansen", "Varga"]
COMPANIES = ["Nordlund Logistics", "Brightwave Oy", "Kuusamo Foods", "Pohjola Energy", "Lumo Software",
             "Harbor Analytics", "Tervo Print", "Aurora Bank", "Metsa Outdoors", "Sinivuori Cafe", "Valo Studios",
             "Kaleva Travel", "Ruska Books", "Taiga Bikes", "Polar Sound"]
VENDORS = ["Kalevi Catering", "Stagecraft Ltd", "Lasse Sound", "PrintPoint", "Tentti Rentals", "Soihtu Lighting",
           "Pop Photo", "BusLine North"]
THINGS = ["sound system", "stage lighting", "catering trays", "printed programmes", "marquee tents", "name badges",
          "photo booth", "shuttle buses"]
TASKS = ["ticket sales", "stage setup", "volunteer coordination", "poster design", "sponsor liaison", "first aid",
         "cloakroom", "social media coverage", "guest registration", "cleanup crew"]
STREETS = ["Koivukatu", "Kuusitie", "Mantykuja", "Lehtikuja", "Pihlajapolku", "Tammikatu", "Rantatie", "Haapatie"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]

# unanswerable questions: events that do not exist in the corpus, and general-knowledge questions
NEW_EVENTS = ["Midnight Sun Festival", "Lantern Night", "Harvest Market", "Robotics Expo", "Poetry Slam", "Ski Trip",
              "Film Festival", "Quiz Night", "Chess Tournament", "Beach Party"]
OFF_TOPIC = ["What is the capital of Australia?", "How do I bake sourdough bread?", "Who won the 2018 football World Cup?",
             "What is the boiling point of water at altitude?", "How many moons does Jupiter have?",
             "Explain how a transformer neural network works.", "What is the best way to learn the guitar?",
             "Who painted the Mona Lisa?", "How far is the Moon from Earth?", "What is the square root of 1764?"]

# fact key -> (sentence, question, answer-from-values); {event}/{year} are always available
FACT_TEMPLATES = {
    "booking": ("The venue booking reference for {event} {year} is {code}.",
                "What is the venue booking reference for {event} {year}?", "{code}"),
    "budget": ("The approved budget for {event} {year} is {amount} euros.",
               "What is the approved budget for {event} {year}?", "{amount}"),
    "sponsor": ("{company} pledged {amount} euros as a sponsor of {event} {year}.",
                "How much did {company} pledge as a sponsor of {event} {year}?", "{amount}"),
    "responsible": ("{person} is responsible for {task} at {event} {year}.",
                    "Who is responsible for {task} at {event} {year}?", "{person}"),
    "deadline": ("The deadline for the {event} {year} {what} is {date}.",
                 "What is the deadline for the {event} {year} {what}?", "{date}"),
    "vendor": ("{vendor} will supply the {thing} for {event} {year}, order number {code}.",
               "What is the order number for the {thing} supplied by {vendor} for {event} {year}?", "{code}"),
}
# which fact kinds each drive's documents contain
DRIVE_FACTS = {
    "leaders": ["budget", "deadline", "responsible", "booking"], "archive": ["budget", "sponsor", "booking", "vendor", "deadline"],
    "members": ["deadline", "booking"], "board": ["budget", "deadline", "responsible"],
    "com_flc": ["sponsor", "budget", "deadline", "responsible"], "com_ac": ["booking", "responsible", "deadline", "vendor"],
}
DEADLINE_WHATS = ["volunteer sign-up", "poster design", "ticket pre-sale", "sponsor report", "venue payment"]
FACTS = {"leaders": 10, "archive": 12, "members": 20, "board": 15, "com_flc": 15, "com_ac": 15}
# files per drive: (kind, count, folder; {y} = year, {slug} = event). Folders nest up to four levels.
LAYOUT = {
    "leaders": [("minutes", 8, "leader-meetings/{y}"), ("plan", 6, "strategy/{y}"), ("budget", 3, "budgets/{y}"),
                ("slides", 3, "strategy/{y}/presentations"), ("report", 4, "handover/{y}"), ("contacts", 2, "coordination"),
                ("notes", 2, "coordination/notes")],
    "archive": [("minutes", 10, "board-minutes/{y}"), ("report", 8, "annual-reports/{y}"), ("plan", 8, "past-events/{y}/{slug}"),
                ("budget", 6, "past-events/{y}/{slug}/finance"), ("slides", 4, "past-events/{y}/{slug}"),
                ("contacts", 2, "legal/contacts"), ("notes", 2, "legal")],
    "board": [("minutes", 12, "meetings/{y}"), ("plan", 8, "strategy/{y}"), ("budget", 6, "finance/{y}"),
              ("slides", 4, "reports/{y}/presentations"), ("report", 5, "reports/{y}"), ("contacts", 3, "hr/contacts"), ("notes", 3, "hr")],
    "com_flc": [("minutes", 10, "meetings/{y}"), ("plan", 8, "events/{y}/{slug}"), ("budget", 6, "finance/{y}"),
                ("slides", 4, "events/{y}/{slug}/slides"), ("report", 5, "reports/{y}"), ("contacts", 4, "partners/contacts"),
                ("notes", 3, "working-notes")],
    "com_ac": [("minutes", 10, "meetings/{y}"), ("plan", 8, "projects/{y}/{slug}"), ("budget", 6, "finance/{y}"),
               ("slides", 4, "projects/{y}/{slug}/slides"), ("report", 5, "reports/{y}"), ("contacts", 4, "partners/contacts"),
               ("notes", 3, "working-notes")],
}
# kind -> (file name suffix, formats, title); {t} is the drive's topic name
EVENT_KINDS = {"plan": ("plan", ["docx", "md"], "{t} plan for {event} {y}"), "budget": ("budget", ["xlsx"], "{t} budget for {event} {y}"),
               "slides": ("update", ["pptx"], "{t} update on {event} {y}"), "report": ("report", ["pdf", "docx"], "{t} report on {event} {y}")}
ALIGNED_SHARE = 0.8  # share of facts planted in files about the fact's own event; the rest are cross-topic mentions
LATEST_CREATED = date(2026, 10, 1)  # fixed, so the corpus does not depend on the day it is generated


@dataclass
class FileSpec:
    path: str  # relative to the corpus root: "<drive path>/<folder>/<file>"
    drive: str
    kind: str  # minutes | plan | report | slides | budget | contacts | note | handbook | newsletter | position
    fmt: str  # md | txt | pdf | docx | xlsx | pptx
    topic: str
    facts: list = field(default_factory=list)  # dicts: key, sentence, question, answer
    pii_lines: list = field(default_factory=list)  # sentences appended verbatim; contain fake PII
    table: list = field(default_factory=list)  # rows for xlsx files
    pii: list = field(default_factory=list)  # [{"type","value"}] every fake PII string in this file
    created: str = ""  # ISO date, stands in for Drive's createdTime
    event: str = ""  # set when the file is about one event ("Spring Gala") in one year; facts planted here match it
    year: int = 0


@dataclass
class Spec:
    users: dict
    drives: dict
    shares: list
    files: list


def _person(rng, used):
    while True:
        first, last = rng.choice(FIRST), rng.choice(LAST)
        if (first, last) not in used:
            used.add((first, last))
            return first, last


def _pii(rng, first, last):
    uid = f"{first}.{last}".lower()
    return {
        "name": f"{first} {last}",
        "email": f"{uid}@example.org",
        "phone": f"+358 40 555 {rng.randint(1000, 9999)}",
        "address": f"{rng.choice(STREETS)} {rng.randint(1, 60)} {rng.choice('ABC')} {rng.randint(1, 40)}, 00{rng.randint(100, 990)} Helsinki",
    }


def _contact_line(p):
    return f"For questions contact {p['name']}, {p['email']}, {p['phone']}."


def _pii_items(p, keys=("email", "phone")):
    return [{"type": k, "value": p[k]} for k in keys]


def build_spec(seed=1):
    rng = random.Random(seed)
    used_names = set()
    drives = {}
    for d, (name, path, contact, _, _) in DRIVES.items():
        roles = {"members": ["*"], "board": [ROLE_BOARD], "leaders": [ROLE_LEADER, ROLE_BOARD], "archive": [ROLE_LEADER, ROLE_BOARD]}.get(d, [ROLE_BOARD])
        drives[d] = {"name": name, "path": path, "members": {"roles": roles}, "contact_role": contact}

    users, people, who, entity_members = {}, {}, {d: [] for d in DRIVES}, {}

    def new_person(role):
        first, last = _person(rng, used_names)
        uid = f"{first}.{last}".lower()
        users[uid] = {"roles": [role]}
        people[uid] = _pii(rng, first, last)
        return uid

    who["board"] = [new_person(ROLE_BOARD) for _ in range(BOARD_SIZE)]
    for e in ENTITIES:  # a leader is a member of the own committee's drive by name; roles stay the three plain ones
        leaders = [new_person(ROLE_LEADER) for _ in range(LEADERS_PER_ENTITY)]
        entity_members[e] = [new_person(ROLE_MEMBER) for _ in range(MEMBERS_PER_ENTITY)]
        drives[e]["members"]["users"] = sorted(leaders)
        who[e] = leaders + entity_members[e]
        who["leaders"] += leaders
    who["archive"] = who["leaders"] + who["board"]
    who["members"] = sorted(users)

    used_codes, used_keys = set(), set()
    years_of = lambda drive: ARCHIVE_YEARS if drive == "archive" else YEARS

    def code():
        while True:
            c = f"{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}-{rng.randint(1000, 9999)}-{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}"
            if c not in used_codes:
                used_codes.add(c)
                return c

    def make_fact(drive, fixed_event="", fixed_year=0):
        for _ in range(100):
            key = rng.choice(DRIVE_FACTS[drive])
            event, year = (fixed_event, fixed_year) if fixed_event else (rng.choice(EVENTS), rng.choice(years_of(drive)))
            v = {"event": event, "year": year}
            if key in ("booking", "vendor"):
                v["code"] = code()
            if key == "vendor":
                v.update(vendor=rng.choice(VENDORS), thing=rng.choice(THINGS))
            if key in ("budget", "sponsor"):
                v["amount"] = str(rng.randrange(500, 30000, 50))
            if key == "sponsor":
                v["company"] = rng.choice(COMPANIES)
            if key == "responsible":
                v.update(person=people[rng.choice(who[drive])]["name"], task=rng.choice(TASKS))
            if key == "deadline":
                v.update(what=rng.choice(DEADLINE_WHATS), date=f"{rng.randint(1, 28)} {rng.choice(MONTHS)} {year}")
            ident = (key, event, year, v.get("what"), v.get("task"), v.get("company"), v.get("thing"), v.get("vendor"))
            ikey = (key, event, year) if key in ("booking", "budget") else ident
            if ikey in used_keys:
                continue
            used_keys.add(ikey)
            sentence, question, answer = FACT_TEMPLATES[key]
            return {"key": key, "sentence": sentence.format(**v), "question": question.format(**v), "answer": answer.format(**v)}
        raise RuntimeError("could not make a unique fact")

    files = []

    def add(drive, folder, name, kind, fmt, topic, **kw):
        files.append(FileSpec(path=f"{DRIVES[drive][1]}/{folder}/{name}.{fmt}", drive=drive, kind=kind, fmt=fmt, topic=topic, **kw))

    def drive_files(d):
        t, years = DRIVES[d][3], years_of(d)
        for kind, n, folder in LAYOUT[d]:
            if kind == "minutes":
                for y, m in rng.sample([(y, m) for y in years for m in range(12)], n):
                    add(d, folder.format(y=y), f"{y}-{m + 1:02d}-{d}-meeting", "minutes", rng.choice(["md", "pdf", "docx"]),
                        f"{t} meeting, {MONTHS[m]} {y}")
            elif kind in EVENT_KINDS:
                suffix, fmts, title = EVENT_KINDS[kind]
                for event in rng.sample(EVENTS, n):
                    y, slug = rng.choice(years), event.lower().replace(" ", "-")
                    rows = ([("Item", "Amount EUR")] + [(w.capitalize(), rng.randrange(100, 5000, 10)) for w in rng.sample(THINGS + TASKS, 6)]
                            if kind == "budget" else [])
                    add(d, folder.format(y=y, slug=slug), f"{slug}-{y}-{suffix}", kind, rng.choice(fmts),
                        title.format(t=t, event=event, y=y), table=rows, event=event, year=y)
            elif kind == "contacts":
                for i in range(n):
                    group = [people[u] for u in rng.sample(who[d], min(4, len(who[d])))]
                    group += [_pii(rng, rng.choice(FIRST), rng.choice(LAST)) for _ in range(rng.randint(3, 6))]  # external contacts
                    rows = [("Name", "Email", "Phone", "Address")] + [(p["name"], p["email"], p["phone"], p["address"]) for p in group]
                    pii = [x for p in group for x in _pii_items(p, ("email", "phone", "address"))]
                    add(d, folder, f"contact-list-{i + 1}", "contacts", rng.choice(["xlsx", "xlsx", "md"]), f"{t} contact list {i + 1}",
                        table=rows, pii=pii)
            else:
                for i in range(n):
                    add(d, folder, f"notes-{i + 1}", "note", "txt", f"{t} working notes {i + 1}")

    for d in LAYOUT:
        drive_files(d)
    for i in range(8):
        add("members", "positions", f"open-position-{i + 1}", "position", "md", f"Open position {i + 1} in the association")
    for i in range(20):
        y, m = rng.choice(YEARS), rng.randrange(12)
        add("members", f"newsletters/{y}", f"newsletter-{y}-{m + 1:02d}-{i}", "newsletter", rng.choice(["md", "pdf"]),
            f"Association newsletter, {MONTHS[m]} {y}")
    for folder, name in [("info/guides", "handbook"), ("info/guides", "faq"), ("info/guides", "code-of-conduct"),
                         ("info/guides", "membership-guide"), ("info/guides", "how-to-join-a-committee"),
                         ("info", "event-calendar-2025"), ("info", "event-calendar-2026"), ("info", "history")]:
        add("members", folder, name, "handbook", "md", f"Association {name.replace('-', ' ')}")
    for i in range(24):
        fmt = rng.choice(["md", "pdf", "docx"])
        event, y = rng.choice(EVENTS), rng.choice(YEARS)
        add("members", f"events/{y}", f"event-announcement-{i + 1}", "handbook", fmt, f"Announcement for {event} {y}", event=event, year=y)

    # plant facts: one per host file; ALIGNED_SHARE of them in files about the fact's own event (cross-topic mentions
    # such as meeting minutes make up the rest and are tagged in qa.jsonl)
    def plant(drive, n):
        hosts = [f for f in files if f.drive == drive and f.kind != "contacts"]
        about_event, free = [f for f in hosts if f.event], [f for f in hosts if not f.event]
        k = round(n * ALIGNED_SHARE)
        for f in rng.sample(about_event, k) + rng.sample(free, n - k):
            f.facts.append(make_fact(drive, f.event, f.year))

    for drive, n in FACTS.items():
        plant(drive, n)
    for f in files:  # fake PII sentences in some prose files, a fake IBAN in some budgets
        if f.kind in ("minutes", "plan", "report") and rng.random() < 0.35:
            p = people[rng.choice(sorted(people))]
            f.pii_lines.append(_contact_line(p))
            f.pii += _pii_items(p)
        if f.kind == "budget" and rng.random() < 0.5:
            iban = f"FI{rng.randint(10, 99)} {rng.randint(1000, 9999)} {rng.randint(1000, 9999)} {rng.randint(1000, 9999)} {rng.randint(10, 99)}"
            f.table.append(("Payment account (IBAN)", iban))
            f.pii.append({"type": "iban", "value": iban})

    # shares: subfolder grants to individual people, a role grant, an org-wide folder, then single-file grants
    policy = Policy(users, drives, [])
    folders = lambda drive, depth: sorted({"/".join(f.path.split("/")[:depth]) for f in files if f.drive == drive and f.path.count("/") > depth})
    other = {"com_flc": "com_ac", "com_ac": "com_flc"}
    shares = []
    for e in ENTITIES:  # two year folders to a few own committee members, one event folder to a member of the other committee
        for folder in rng.sample(folders(e, 3), 2):
            shares.append({"path": folder, "users": sorted(rng.sample(entity_members[e], rng.randint(2, 3)))})
        shares.append({"path": rng.choice(folders(e, 4)), "users": [rng.choice(entity_members[other[e]])]})
    role_folder, *user_folders = rng.sample(folders("archive", 3), 3)  # one year of the archive to every committee member, two to a few
    shares.append({"path": role_folder, "roles": [ROLE_MEMBER]})
    for folder in user_folders:
        shares.append({"path": folder, "users": sorted(rng.sample(sorted(u for u in users if ROLE_MEMBER in users[u]["roles"]), 3))})
    shares.append({"path": f"{DRIVES['leaders'][1]}/handover", "users": sorted(rng.sample(entity_members["com_flc"] + entity_members["com_ac"], 2))})
    shares.append({"path": rng.choice(folders("board", 3)), "users": sorted(rng.sample(who["leaders"], 2))})
    shares.append({"path": rng.choice(folders("com_ac", 3)), "users": ["*"]})  # org-wide folder inside a restricted drive
    restricted = [f for f in files if f.drive != "members"]
    with_facts = [f for f in restricted if f.facts]
    others = [f for f in restricted if not f.facts]
    for f in rng.sample(with_facts, 30) + rng.sample(others, 15):
        outsiders = [u for u in users if f.drive not in policy.drives_with_access(u)]
        shares.append({"path": f.path, "users": sorted(rng.sample(outsiders, rng.randint(1, 3)))})

    # creation dates from a separate generator so the rest of the corpus is unchanged by them
    dates = random.Random(seed + 7919)
    for f in files:
        ym = re.search(r"(20\d\d)-(\d\d)", f.path)
        year = int(ym[1]) if ym else int((re.search(r"20\d\d", f.topic) or [dates.choice(years_of(f.drive))])[0])
        month = int(ym[2]) if ym else dates.randint(1, 12)
        f.created = min(date(year, month, dates.randint(1, 28)), LATEST_CREATED).isoformat()

    return Spec(users=users, drives=drives, shares=shares, files=files)


def build_negatives(seed=1):
    """Questions the corpus cannot answer: [{"question", "kind"}]. Separate random stream, so the corpus is unaffected."""
    rng = random.Random(seed + 104729)
    out = []
    for i in range(25):
        v = {"event": NEW_EVENTS[i % len(NEW_EVENTS)], "year": rng.choice(YEARS), "task": rng.choice(TASKS),
             "what": rng.choice(DEADLINE_WHATS), "company": rng.choice(COMPANIES), "vendor": rng.choice(VENDORS),
             "thing": rng.choice(THINGS)}
        key = rng.choice(list(FACT_TEMPLATES))
        out.append({"question": FACT_TEMPLATES[key][1].format(**v), "kind": "unknown-event"})
    return out + [{"question": q, "kind": "off-topic"} for q in OFF_TOPIC]


ASSOCIATION_QUESTIONS = [
    ("What positions are currently open in the association?", ["Members/positions/"]),
    ("What does a volunteer position involve and how do I apply?", ["Members/positions/"]),
    ("How do I join a committee in the association?", ["Members/info/guides/how-to-join-a-committee.md"]),
    ("What is the association's code of conduct?", ["Members/info/guides/code-of-conduct.md"]),
    ("How does membership work?", ["Members/info/guides/membership-guide.md"]),
    ("What is the history of the association?", ["Members/info/history.md"]),
    ("What events are planned for 2025?", ["Members/info/event-calendar-2025.md"]),
    ("What events are planned for 2026?", ["Members/info/event-calendar-2026.md"]),
    ("Where can I find answers to frequently asked questions?", ["Members/info/guides/faq.md"]),
    ("What is the association handbook about?", ["Members/info/guides/handbook.md"]),
    ("What news did the association share recently?", ["Members/newsletters/"]),
    ("What do the association newsletters cover?", ["Members/newsletters/"]),
]


def build_general(files, seed=1):
    """General-information questions with the general-drive files that answer them: [{"question","kind","expected"}].

    Event overviews are the hard case: every team also holds plans, budgets and slides for the same event.
    Separate random stream, so the corpus is unaffected.
    """
    rng = random.Random(seed + 15485863)
    out = [{"question": q, "kind": "general-association", "expected": exp} for q, exp in ASSOCIATION_QUESTIONS]
    announced = {}
    for f in files:
        if f.drive == "members" and f.event:
            announced.setdefault((f.event, f.year), []).append(f.path)
    for i, (event, year) in enumerate(rng.sample(sorted(announced), min(12, len(announced)))):
        q = (f"Tell me about {event} {year}", f"What is {event} {year} and when does it take place?")[i % 2]
        out.append({"question": q, "kind": "general-event", "expected": announced[event, year]})
    return out
