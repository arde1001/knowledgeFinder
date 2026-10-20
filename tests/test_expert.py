import json

import pytest

from test_retriever import env, make  # noqa: F401  (env is a pytest fixture)

from kf import account
from kf.expert import NOTHING, Expert, prompt_tokens
from kf.finder import Config


class FakeChat:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, messages, **kw):
        self.calls.append(messages)
        return self.replies.pop(0)


def expert(env, chat, **kw):
    finder, retriever = make(env)
    return finder, Expert(finder, retriever, chat=chat, **kw)


def everything_sent(chat):
    return json.dumps(chat.calls)


def test_answer_lists_only_cited_sources_with_path_drive_and_date(env):
    chat = FakeChat("The gala is at Harbour Hall [1].")
    _, e = expert(env, chat)
    r = e.ask("bob", "gala venue Harbour Hall")
    assert r.sources == [(1, "events/gala.md", "Events", "2025-01-01")]
    assert r.text == "The gala is at Harbour Hall [1].\n\nSources:\n[1] events/gala.md (Events, created 2025-01-01)"


def test_uncited_or_invented_reference_adds_no_source(env):
    _, e = expert(env, FakeChat("Not sure [7]."))
    assert e.ask("bob", "gala venue").sources == []


def test_model_never_sees_pii_or_unreadable_files(env):
    chat = FakeChat("ok [1]")
    _, e = expert(env, chat)
    e.ask("bob", "gala venue Harbour Hall and the hackathon budget")
    sent = everything_sent(chat)
    assert "Harbour Hall" in sent
    for secret in ("555", "anna.virtanen", "Koivukatu", "9000", "hackathon budget of"):
        assert secret not in sent


def test_nothing_found_says_so_and_lists_the_drives_searched(env):
    chat = FakeChat("NOT_FOUND")
    _, e = expert(env, chat)
    r = e.ask("dave", "hackathon budget")  # dave reads only the general drive
    assert r.answer == NOTHING and r.sources == []
    assert r.text.startswith(f"{NOTHING} I searched the drives you can open (General).")
    assert "none found" in chat.calls[0][-1]["content"]


def test_denial_notice_is_added_by_code_and_not_shown_to_the_model(env):
    chat = FakeChat("It is in the general FAQ [1].")
    finder, e = expert(env, chat)
    finder.config = Config(min_score=0.1, denial_mode="best")
    r = e.ask("bob", "hackathon budget approved by the board")
    assert r.denial and r.text.endswith("File(s) inside Drive Board may match; you do not have permission. Ask: Chair")
    sent = everything_sent(chat)
    assert "Board" not in sent and "Chair" not in sent
    assert "budget.md" not in r.text and "9000" not in r.text


def test_denial_alone_when_nothing_readable_matches(env):
    finder, e = expert(env, FakeChat("NOT_FOUND"))
    finder.config = Config(min_score=0.99, denial_mode="best")
    r = e.ask("bob", "hackathon budget approved by the board")
    assert r.text == f"{NOTHING} I searched the drives you can open (Events, General).\n\nFile(s) inside Drive Board may match; you do not have permission. Ask: Chair"


def test_follow_up_is_rewritten_with_history_and_searched_standalone(env):
    chat = FakeChat("It is Harbour Hall [1].", "Where is the gala venue Harbour Hall?", "Yes [1].")
    _, e = expert(env, chat)
    e.ask("bob", "gala venue Harbour Hall")
    r = e.ask("bob", "where is that again?")
    assert len(chat.calls) == 3 and r.query == "Where is the gala venue Harbour Hall?"
    rewrite_prompt = json.dumps(chat.calls[1])
    assert "gala venue Harbour Hall" in rewrite_prompt and "It is Harbour Hall [1]." in rewrite_prompt
    final = chat.calls[2]
    assert [m["role"] for m in final] == ["system", "user", "assistant", "user"]
    assert "Excerpts:" not in final[1]["content"]  # history keeps questions and answers, never excerpts
    assert final[3]["content"].endswith("Question: Where is the gala venue Harbour Hall?")


def test_runaway_rewrite_falls_back_to_the_users_words(env):
    chat = FakeChat("Harbour Hall [1].", "x" * 2000, "Hall [1].")
    _, e = expert(env, chat)
    e.ask("bob", "gala venue Harbour Hall")
    assert e.ask("bob", "gala venue?").query == "gala venue?"


def test_history_keeps_only_the_last_turns_and_reset_clears_it(env):
    chat = FakeChat(*["a [1]"] + ["gala venue Harbour Hall", "a [1]"] * 6)
    _, e = expert(env, chat, history_turns=2)
    for _ in range(4):
        e.ask("bob", "gala venue Harbour Hall")
    assert len(e.history) == 2
    e.reset()
    assert not e.history


def test_model_saying_not_found_gives_the_standard_message_and_no_sources(env):
    _, e = expert(env, FakeChat("NOT_FOUND"))
    r = e.ask("bob", "gala venue Harbour Hall")
    assert r.answer == NOTHING and r.sources == [] and r.text.startswith(NOTHING)


def test_not_found_marker_after_an_explanation_is_not_shown(env):
    _, e = expert(env, FakeChat("The venue is not mentioned in the excerpts [1]. NOT_FOUND"))
    r = e.ask("bob", "gala venue Harbour Hall")
    assert r.answer == NOTHING and r.sources == [] and "NOT_FOUND" not in r.text


def test_account_questions_are_answered_from_the_account_block_without_citations(env):
    chat = FakeChat("You have the role events [9].")
    _, e = expert(env, chat)
    r = e.ask("bob", "What is my role?")
    prompt = chat.calls[0][-1]["content"]
    assert "- Your roles: events" in prompt and "- Drives you can open: Events" in prompt and "General" in prompt
    assert "Board" not in prompt
    assert r.text == "You have the role events."  # a citation that points at no excerpt is removed


def test_drive_named_in_the_question_adds_its_folder_labels(env):
    finder, _ = expert(env, FakeChat())
    plain = account.build(finder, "bob", "what is in the general folder?")
    assert plain.folders == []  # the test corpus has no subfolders; the drive itself is labelled
    finder.fm["folders"]["general/info"] = {"description": "Guides"}
    finder.live["general/info/a.md"] = finder.live["general/faq.md"]
    finder._live_set.add("general/info/a.md")
    finder._readable.clear()
    assert account.build(finder, "bob", "what is in the general folder?").folders == [("general/info", "Guides")]
    assert account.build(finder, "bob", "what is in the events folder?").folders == []


def test_shared_files_list_the_drive_but_never_its_labels(env):
    finder, _ = make(env, shares=[{"path": "board/budget.md", "users": ["bob"]}])
    info = account.build(finder, "bob", "what is in the board folder?")
    assert info.shared == ["Board"] and info.folders == [] and "Board" not in [n for _, n, _ in info.drives]
    assert "Folder board" not in info.text()


def test_a_label_is_hidden_when_something_below_it_is_unreadable(env):
    finder, _ = make(env)
    everything = set(finder._live_set)
    finder._readable_set = lambda user: everything - {"general/faq.md"}
    drives = account.build(finder, "bob", "general").drives
    assert [(n, l) for _, n, l in drives if n == "General"] == [("General", "")]


def test_short_drive_names_match_only_exactly(env):
    assert account._named("is it ready?", "it", "IT") is False
    assert account._named("what is in IT?", "it", "IT") is True


def test_naming_a_drive_you_cannot_open_adds_its_notice_but_a_bare_word_does_not(env):
    chat = FakeChat("I cannot tell what it contains.", "Which board events are coming up?", "Some events [9].")
    _, e = expert(env, chat)
    r = e.ask("bob", "What is in the Board folder?")
    assert "what it contains is unknown to you" in chat.calls[0][-1]["content"]
    assert r.text.endswith("File(s) inside Drive Board may match; you do not have permission. Ask: Chair")
    assert e.ask("bob", "Which board events are coming up?").denial is None  # the word alone is not a request for that drive
    assert "Board" not in chat.calls[2][-1]["content"].split("Excerpts:")[0]


def test_chat_refuses_an_unknown_user_instead_of_answering_nothing_to_everything(env, monkeypatch):
    import sys

    from kf import expert as module

    finder, _ = make(env)
    monkeypatch.setattr(module, "load_finder", lambda data, config: finder)
    monkeypatch.setattr(sys, "argv", ["expert", "--user", "nobody"])
    with pytest.raises(SystemExit, match="unknown user 'nobody'"):
        module.main()


def test_asked_about_wording():
    assert account._asked_about("what is in the finance folder?", "finance", "Finance")
    assert account._asked_about("show me drive Finance", "finance", "Finance")
    assert not account._asked_about("what are the finance plans?", "finance", "Finance")


def test_prompt_guard_drops_old_turns_before_excerpts(env):
    _, e = expert(env, FakeChat("At Harbour Hall [1]."), num_ctx=100_000)
    base = prompt_tokens(e.ask("bob", "gala venue Harbour Hall").prompts[-1])
    chat = FakeChat("gala venue Harbour Hall", "At Harbour Hall [1].")
    _, e = expert(env, chat, num_ctx=base + 100 + 50, answer_tokens=100)
    e.history.append(("old question", "y" * 6000))
    r = e.ask("bob", "gala venue Harbour Hall")
    sent = json.dumps(r.prompts[-1])
    assert "yyyy" not in sent and "Harbour Hall" in sent and r.sources  # history went, the excerpt stayed
    assert prompt_tokens(r.prompts[-1]) + 100 <= base + 150


def test_prompt_guard_drops_excerpts_when_even_one_turn_does_not_fit(env):
    _, e = expert(env, FakeChat("At Harbour Hall [1]."), num_ctx=100_000)
    base = prompt_tokens(e.ask("bob", "gala venue Harbour Hall").prompts[-1])
    _, e = expert(env, FakeChat("At Harbour Hall [1]."), num_ctx=base + 100 - 5, answer_tokens=100)
    r = e.ask("bob", "gala venue Harbour Hall")
    assert "none found" in r.prompts[-1][-1]["content"] and r.sources == []  # a citation of a dropped excerpt lists nothing
