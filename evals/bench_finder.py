"""Finder benchmark: personas x questions, leak assertions, ranking, denial and unanswerable-question metrics.

    PYTHONPATH=src .venv/bin/python evals/bench_finder.py [--config finder.yaml] [--sweep] [--out evals/finder_benchmark.md]

Personas are built from the test corpus (a committee member, two leaders of different committees, the person with most shares); `superuser` (a board member: reads every drive) and `guest` (no roles) exist only here.
Rankings are retrieved once per persona and question, so thresholds can be swept without searching again.
Any leak (a source the persona cannot read or that is not live, a denial with extra fields or for a drive the persona
belongs to) aborts the run.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import yaml

from kf import filemap, llm, profiles
from kf.corpus.spec import ROLE_BOARD, ROLE_LEADER, ROLE_MEMBER
from kf.finder import Config, Finder
from kf.indexer import Index, index_dir
from kf.perms import Policy

DATA = Path("testdata")


def config(path=None):
    """Finder thresholds: the given file, or the active profile's (KF_PROFILE)."""
    return Config.load(path or profiles.current().finder)


def load(config):
    users = yaml.safe_load((DATA / "users.yaml").read_text(encoding="utf-8"))["users"]
    drives = yaml.safe_load((DATA / "drives.yaml").read_text(encoding="utf-8"))["drives"]
    shares = yaml.safe_load((DATA / "shares.yaml").read_text(encoding="utf-8"))["shares"]
    share_count = {u: sum(u in s.get("users", []) for s in shares) for u in users}
    leaders = [u for u in sorted(users) if users[u]["roles"] == [ROLE_LEADER]]
    committee = lambda u: next((d for d, v in drives.items() if u in v["members"].get("users", [])), None)  # the drive a leader reads by name
    personas = {
        "superuser": "superuser",
        "member": min((u for u in sorted(users) if users[u]["roles"] == [ROLE_MEMBER]), key=lambda u: share_count[u]),
        "leader": leaders[0],
        "other_leader": next(u for u in leaders if committee(u) != committee(leaders[0])),
        "sharee": max(sorted(users), key=lambda u: share_count[u]),
        "guest": "guest",
    }
    everyone = {**users, "superuser": {"roles": [ROLE_BOARD]}, "guest": {"roles": []}}
    policy = Policy(everyone, drives, shares)
    cache, embed_times = {}, []

    def embed_query(text):
        if text not in cache:
            t0 = time.perf_counter()
            cache[text] = llm.embed_query(text, model)
            embed_times.append(time.perf_counter() - t0)
        return cache[text]

    index = Index.load(index_dir(DATA, profiles.current().embed_model), embed_query=embed_query)
    model = index.meta["model"]
    finder = Finder(policy, filemap.load(DATA / "filemap.json"), index, DATA / "drive", config)
    return policy, finder, personas, everyone, embed_times


def read_jsonl(name):
    return [json.loads(l) for l in (DATA / name).read_text(encoding="utf-8").splitlines()]


def retrieve_all(finder, personas, qa, negatives, lex_weight=None, general=()):
    raws, rank_times = {}, []
    for name, user in personas.items():
        for kind, items in (("qa", qa), ("neg", negatives), ("gen", general)):
            for i, item in enumerate(items):
                raws[name, kind, i] = finder.retrieve(user, item["question"], lex_weight)
                rank_times.append(finder.timing["rank"])
    return raws, rank_times


def evaluate(finder, policy, personas, qa, negatives, raws, cfg, general=()):
    out = {}
    for name, user in personas.items():
        m = dict(ranks=[], aligned=[], restricted=0, recall=0, wrong=0, extra=0, readable=0, nsrc=[], leaks=0,
                 neg_total={"unknown-event": 0, "off-topic": 0}, neg_empty={"unknown-event": 0, "off-topic": 0}, neg_notice=0,
                 gen_total={"general-association": 0, "general-event": 0}, gen_notice={"general-association": 0, "general-event": 0},
                 gen_found=0)
        members = policy.drives_with_access(user)

        def check(res):
            m["leaks"] += sum(not policy.can_read(user, s.path) or s.path not in finder.live for s in res.sources)
            if res.denial:
                d = res.denial.__dict__
                m["leaks"] += set(d) != {"drive", "drive_name", "contact_role"} or res.denial.drive in members

        for i, item in enumerate(qa):
            res = finder.decide(raws[name, "qa", i], cfg)
            check(res)
            if policy.can_read(user, item["path"]):
                m["readable"] += 1
                found = [s.path for s in res.sources]
                m["ranks"].append(found.index(item["path"]) + 1 if item["path"] in found else None)
                m["aligned"].append(item["aligned"])
                m["nsrc"].append(len(found))
                m["extra"] += res.denial is not None
            else:
                m["restricted"] += 1
                m["recall"] += res.denial is not None and res.denial.drive == item["drive"]
                m["wrong"] += res.denial is not None and res.denial.drive != item["drive"]
        for i, item in enumerate(negatives):
            res = finder.decide(raws[name, "neg", i], cfg)
            check(res)
            m["neg_total"][item["kind"]] += 1
            m["neg_empty"][item["kind"]] += not res.sources
            m["neg_notice"] += res.denial is not None
        for i, item in enumerate(general):
            res = finder.decide(raws[name, "gen", i], cfg)
            check(res)
            m["gen_total"][item["kind"]] += 1
            m["gen_notice"][item["kind"]] += res.denial is not None
            m["gen_found"] += any(s.path.startswith(e) for s in res.sources for e in item["expected"])
        out[name] = m
    leaks = sum(m["leaks"] for m in out.values())
    assert leaks == 0, f"{leaks} permission leaks"
    return out


def summarise(m):
    r, n = m["ranks"], max(len(m["ranks"]), 1)
    found = [x for x in r if x]
    ratio = lambda a, b: a / b if b else float("nan")
    return {
        "readable_q": len(r), "found": len(found) / n, "hit1": sum(x == 1 for x in found) / n,
        "mrr": sum(1 / x for x in found) / n, "opened": statistics.mean(x - 1 for x in found) if found else float("nan"),
        "found_aligned": ratio(sum(1 for x, a in zip(r, m["aligned"]) if x and a), sum(m["aligned"])),
        "found_cross": ratio(sum(1 for x, a in zip(r, m["aligned"]) if x and not a), sum(not a for a in m["aligned"])),
        "avg_sources": statistics.mean(m["nsrc"]) if m["nsrc"] else float("nan"),
        "restricted_q": m["restricted"], "recall": ratio(m["recall"], m["restricted"]),
        "wrong": ratio(m["wrong"], m["restricted"]), "extra": ratio(m["extra"], m["readable"]),
        "neg_empty_event": ratio(m["neg_empty"]["unknown-event"], m["neg_total"]["unknown-event"]),
        "neg_empty_off": ratio(m["neg_empty"]["off-topic"], m["neg_total"]["off-topic"]),
        "neg_notice": ratio(m["neg_notice"], sum(m["neg_total"].values())),
        "gen_notice_assoc": ratio(m["gen_notice"]["general-association"], m["gen_total"]["general-association"]),
        "gen_notice_event": ratio(m["gen_notice"]["general-event"], m["gen_total"]["general-event"]),
        "gen_found": ratio(m["gen_found"], sum(m["gen_total"].values())),
    }


def table(results, personas, users):
    f = lambda x: "-" if x != x else f"{x:.2f}"
    lines = ["| persona (roles) | readable q | found | hit@1 | MRR | opened before right | sources/q | restricted q | notice recall | wrong drive | extra notice | unknown-event empty | off-topic empty | notice on unanswerable | notice on general (association / event) | general answer found |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, m in results.items():
        s = summarise(m)
        roles = "+".join(users[personas[name]]["roles"]) or "none"
        lines.append(f"| {name} ({roles}) | {s['readable_q']} | {f(s['found'])} | {f(s['hit1'])} | {f(s['mrr'])} | {f(s['opened'])} | "
                     f"{f(s['avg_sources'])} | {s['restricted_q']} | {f(s['recall'])} | {f(s['wrong'])} | {f(s['extra'])} | "
                     f"{f(s['neg_empty_event'])} | {f(s['neg_empty_off'])} | {f(s['neg_notice'])} | "
                     f"{f(s['gen_notice_assoc'])} / {f(s['gen_notice_event'])} | {f(s['gen_found'])} |")
    return "\n".join(lines)


def sweep(finder, policy, personas, qa, negatives, raws, base):
    from dataclasses import replace

    lines = ["", "### Source thresholds (superuser, member): found / hit@1 / sources per question / unanswerable questions returning nothing", "",
             "| ratio | min_score | su found | su hit@1 | su sources/q | su unknown-event empty | su off-topic empty | member found | member hit@1 |", "|---|---|---|---|---|---|---|---|---|"]
    for ratio in (0.8, 0.9, 0.95, 1.0):
        for min_score in (0.0, 0.5, 0.55, 0.6, 0.65, 0.7):
            r = evaluate(finder, policy, personas, qa, negatives, raws, replace(base, ratio=ratio, min_score=min_score))
            su, me = summarise(r["superuser"]), summarise(r["member"])
            lines.append(f"| {ratio} | {min_score} | {su['found']:.2f} | {su['hit1']:.2f} | {su['avg_sources']:.2f} | {su['neg_empty_event']:.2f} | "
                         f"{su['neg_empty_off']:.2f} | {me['found']:.2f} | {me['hit1']:.2f} |")
    lines += ["", "### Denial rule (member, other_leader, sharee, guest pooled)", "",
              "| K | N | min_denial_score | recall | wrong drive | extra notice (answer readable) | notice on unanswerable |", "|---|---|---|---|---|---|---|"]
    for K in (3, 5, 7, 10):
        for N in (1, 2, 3):
            for mds in (0.0, 0.6, 0.65, 0.7):
                if N > K:
                    continue
                r = evaluate(finder, policy, personas, qa, negatives, raws, replace(base, K=K, N=N, min_denial_score=mds))
                pool = [r[p] for p in ("member", "other_leader", "sharee", "guest")]
                tot = lambda k: sum(m[k] for m in pool)
                neg_n = sum(sum(m["neg_total"].values()) for m in pool)
                lines.append(f"| {K} | {N} | {mds} | {tot('recall') / tot('restricted'):.2f} | {tot('wrong') / tot('restricted'):.2f} | "
                             f"{tot('extra') / tot('readable'):.2f} | {tot('neg_notice') / neg_n:.2f} |")
    return "\n".join(lines)


def lexical_sweep(finder, policy, personas, qa, negatives, base):
    """Compare BM25 weights. Score thresholds are re-derived per weight: just below the weakest real question's top
    score (superuser), so no real question is lost on this set and the rest measures rejection."""
    from dataclasses import replace

    lines = ["| weight | threshold | top-5 found | hit@1 | MRR | opened | found @ratio 0.95 | sources/q | unknown-event empty | off-topic empty | "
             "K=3,N=2: recall / wrong / extra / on unanswerable | K=1,N=1 (best match restricted): recall / wrong / extra / on unanswerable |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for w in (0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2):
        raws, _ = retrieve_all(finder, personas, qa, negatives, w)
        tops = [raws["superuser", "qa", i].readable[0][1] for i in range(len(qa))]
        t = round(min(tops) - 0.03, 2)
        cfg = replace(base, ratio=0.95, min_score=t, min_denial_score=t, lex_weight=w)
        full = summarise(evaluate(finder, policy, personas, qa, negatives, raws, replace(cfg, ratio=0.0, min_score=0.0))["superuser"])
        r = evaluate(finder, policy, personas, qa, negatives, raws, cfg)
        su = summarise(r["superuser"])
        denial = []
        for K, N in ((3, 2), (1, 1)):
            r = evaluate(finder, policy, personas, qa, negatives, raws, replace(cfg, K=K, N=N))
            pool = [r[p] for p in ("member", "other_leader", "sharee", "guest")]
            tot = lambda k: sum(m[k] for m in pool)
            neg_n = sum(sum(m["neg_total"].values()) for m in pool)
            denial.append(f"{tot('recall') / tot('restricted'):.2f} / {tot('wrong') / tot('restricted'):.2f} / "
                          f"{tot('extra') / tot('readable'):.2f} / {tot('neg_notice') / neg_n:.2f}")
        lines.append(f"| {w} | {t} | {full['found']:.3f} | {full['hit1']:.3f} | {full['mrr']:.3f} | {full['opened']:.2f} | {su['found']:.3f} | "
                     f"{su['avg_sources']:.2f} | {su['neg_empty_event']:.2f} | {su['neg_empty_off']:.2f} | {denial[0]} | {denial[1]} |")
    return "\n".join(lines)


def denial_sweep(finder, policy, personas, qa, negatives, general, raws, base):
    """Compare denial rules on the restricted personas: cluster (N of top K) against best-match with a margin guard."""
    from dataclasses import replace

    rules = [("cluster K=3 N=2", dict(denial_mode="cluster", K=3, N=2)), ("cluster K=5 N=2", dict(denial_mode="cluster", K=5, N=2))]
    for mds in (0.87, 0.95, 1.0):
        for margin in (0.0, 0.03, 0.06, 0.1, 0.15, 0.2, 0.3):
            rules.append((f"best, min {mds}, margin {margin}", dict(denial_mode="best", min_denial_score=mds, margin=margin)))
    lines = ["| rule | names the answer's drive | names another drive | notice when the answer is readable | notice on unanswerable | notice on general-association | notice on general-event |",
             "|---|---|---|---|---|---|---|"]
    for label, change in rules:
        r = evaluate(finder, policy, personas, qa, negatives, raws, replace(base, **change), general)
        pool = [r[p] for p in ("member", "other_leader", "sharee", "guest")]
        tot = lambda k: sum(m[k] for m in pool)
        gen = lambda kind, key: sum(m[key][kind] for m in pool)
        lines.append(f"| {label} | {tot('recall') / tot('restricted'):.2f} | {tot('wrong') / tot('restricted'):.2f} | "
                     f"{tot('extra') / tot('readable'):.2f} | {tot('neg_notice') / sum(sum(m['neg_total'].values()) for m in pool):.2f} | "
                     f"{gen('general-association', 'gen_notice') / gen('general-association', 'gen_total'):.2f} | "
                     f"{gen('general-event', 'gen_notice') / gen('general-event', 'gen_total'):.2f} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="finder thresholds (default: the profile's, KF_PROFILE)")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--lexical", action="store_true", help="compare BM25 weights instead of the normal run")
    ap.add_argument("--denial", action="store_true", help="compare denial rules instead of the normal run")
    ap.add_argument("--out", default=str(Path(__file__).parent / "finder_benchmark.md"))
    a = ap.parse_args()
    cfg = config(a.config)
    policy, finder, personas, users, embed_times = load(cfg)
    qa, negatives, general = read_jsonl("qa.jsonl"), read_jsonl("negatives.jsonl"), read_jsonl("general.jsonl")
    if a.lexical:
        text = lexical_sweep(finder, policy, personas, qa, negatives, cfg)
        print(text)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        return
    raws, rank_times = retrieve_all(finder, personas, qa, negatives, general=general)
    if a.denial:
        text = denial_sweep(finder, policy, personas, qa, negatives, general, raws, cfg)
        print(text)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        return
    results = evaluate(finder, policy, personas, qa, negatives, raws, cfg, general)
    text = [f"# Finder benchmark\n\nconfig: {cfg}\n", f"{len(qa)} questions + {len(negatives)} unanswerable + {len(general)} general-information; zero permission leaks (asserted).\n",
            table(results, personas, users),
            f"\nlatency: query embedding {statistics.mean(embed_times) * 1000:.0f} ms mean ({len(embed_times)} unique questions), "
            f"ranking {statistics.mean(rank_times) * 1000:.1f} ms mean / {sorted(rank_times)[int(len(rank_times) * .95)] * 1000:.1f} ms p95 "
            f"over {len(rank_times)} searches"]
    su = summarise(results["superuser"])
    text.append(f"\nsuperuser found: aligned {su['found_aligned']:.2f}, cross-topic {su['found_cross']:.2f}")
    if a.sweep:
        text.append(sweep(finder, policy, personas, qa, negatives, raws, cfg))
    Path(a.out).write_text("\n".join(text) + "\n", encoding="utf-8")
    print("\n".join(text))


if __name__ == "__main__":
    main()
