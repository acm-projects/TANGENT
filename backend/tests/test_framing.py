from debate.fakes import ScriptedBrain, make_deps
from debate.framing import choose_questions, needs_question
from debate.runner import build_resume
from debate.schemas import FrameResult, Question
from tests.helpers import drive, run

Q = [Question(prompt="Measured by what?", options=[{"label": "A"}, {"label": "B"}]), Question(prompt="For whom?"), Question(prompt="third")]
NOTHING = {"criterion_stated": False, "setting_stated": False, "context_resolves": False}
ALL = {"criterion_stated": True, "setting_stated": True, "context_resolves": False}


def test_older_brains_without_checks_keep_their_own_questions():
    assert choose_questions("Is X better?", None, Q) == Q


def test_missing_criterion_or_setting_asks_at_most_two_questions():
    assert choose_questions("Should small teams use microservices instead of a monolith?", {**ALL, "criterion_stated": False}, Q) == Q[:2]
    assert choose_questions("Should small teams use microservices instead of a monolith?", {**ALL, "setting_stated": False}, Q) == Q[:2]


def test_a_clear_topic_never_asks_even_if_the_model_proposed_questions():
    assert choose_questions("Is Postgres faster than MySQL for read-heavy analytics workloads at 1 TB?", ALL, Q) == []


def test_context_that_resolves_it_means_no_question():
    assert choose_questions("Is it worth it?", {**NOTHING, "context_resolves": True}, Q) == []


def test_a_short_vague_topic_asks_even_when_the_model_says_everything_is_stated():
    assert needs_question("Is remote work better?", ALL) is True
    assert needs_question("Is it worth it?", ALL) is True
    assert needs_question("Which one is best?", ALL) is True
    assert needs_question("Is Postgres faster than MySQL for reads?", ALL) is False


def test_when_the_model_proposes_nothing_a_generic_question_is_asked():
    qs = choose_questions("Is remote work better?", NOTHING, [])
    assert len(qs) == 1 and len(qs[0].options) == 4


def test_same_input_gives_the_same_decision_every_time():
    runs = {needs_question("Is remote work better?", dict(ALL)) for _ in range(20)}
    assert runs == {True}


class Checked(ScriptedBrain):
    def __init__(self, checks, **kw):
        super().__init__(**kw)
        self.checks = checks

    async def frame(self, topic, context):
        r = await super().frame(topic, context)
        return FrameResult(proposition=r.proposition, side_briefs=r.side_briefs, questions=self.frame_questions, checks=self.checks)


def test_graph_pauses_when_code_says_ask():
    q = Question(prompt="Measured by what?")
    brain = Checked(NOTHING, frame_questions=[q])
    values, segments, _ = run(drive(make_deps(brain), on_pause=lambda s: build_resume(s.interrupts, {q.id: "cost"})))
    assert [s.status for s in segments] == ["paused", "done"]


def test_graph_does_not_pause_when_code_says_dont_ask_even_if_the_model_proposed_a_question():
    brain = Checked(dict(ALL, context_resolves=True), frame_questions=[Question(prompt="Budget?")])
    values, segments, _ = run(drive(make_deps(brain)))
    assert [s.status for s in segments] == ["done"]
