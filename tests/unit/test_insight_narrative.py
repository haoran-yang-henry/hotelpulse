import json
from datetime import date

import httpx
import pytest

from hotelpulse.insight import narrative
from hotelpulse.insight.facts import Fact, FactSheet, Number
from hotelpulse.insight.llm import ChatClient, Completion, LLMConfig, LLMError


def sheet() -> FactSheet:
    return FactSheet(
        title="Payment success rate by device",
        display="line",
        facts=[
            Fact(
                "anomaly",
                "mobile 23.5% vs 79.0% (-55.5 pp).",
                [Number(23.5, "%"), Number(79.0, "%"), Number(-55.5, "pp")],
                7,
                id="F1",
            ),
            Fact(
                "latest",
                "Visits 1,254; revenue €4,048,105.",
                [Number(1254, ""), Number(4048105.43, "€")],
                2,
                id="F2",
            ),
        ],
        dates={date(2026, 9, 21)},
    )


@pytest.mark.parametrize(
    "text",
    [
        "Mobile fell to 23.5% from 79.0%, a drop of 55.5 pp.",
        "Mobile fell to about 24% (-55.5 percentage points).",
        "1,254 visits and €4.05 million revenue in week 2026-09-21 (21 September).",
        "移动端支付成功率降至23.5%，下降了55.5个百分点。",
        "Mobil sank auf 23,5 % gegenüber 79,0 %.",
        "Over the last 3 weeks things normalised.",
    ],
)
def test_numbers_from_facts_verify(text):
    assert narrative.unverified_numbers([text], sheet()) == []


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        ("Mobile fell to 31.2%.", ["31.2%"]),
        ("Revenue was €5,000.", ["€5,000"]),
        ("1,300 visits.", ["1,300"]),
        ("A 23.5 pp change and 79.0% share are fine, but 42 is not.", ["42"]),
    ],
)
def test_invented_numbers_are_caught(text, bad):
    assert narrative.unverified_numbers([text], sheet()) == bad


def test_context_numbers_are_allowed():
    ctx = {"description": "Below 60 % triggers a data-quality warning."}
    assert narrative.unverified_numbers(["Coverage is below 60%."], sheet(), ctx) == []


class FakeClient:
    model = "fake-model"

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def complete(self, messages):
        self.calls.append(messages)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Completion(json.dumps(answer), 100, 50)


GOOD = {
    "headline": "Mobile payments collapsed to 23.5%.",
    "observations": [{"text": "Only mobile dropped (-55.5 pp).", "fact_ids": ["F1"]}],
    "possible_causes": [{"text": "A checkout bug.", "confidence": "HIGH"}],
    "recommended_actions": ["Check the mobile payment provider logs."],
    "caveats": [],
}


def test_generate_verified_first_try():
    result = narrative.generate(sheet(), {}, "en", FakeClient([GOOD]))
    assert result.mode == "llm" and result.verified and result.attempts == 1
    assert result.narrative.possible_causes[0].confidence == "high"


def test_generate_retries_with_feedback_on_invented_numbers():
    bad = {**GOOD, "headline": "Mobile payments collapsed to 12%."}
    client = FakeClient([bad, GOOD])
    result = narrative.generate(sheet(), {}, "en", client)
    assert result.verified and result.attempts == 2
    assert "12%" in client.calls[1][-1]["content"]
    assert result.prompt_tokens == 200


def test_generate_flags_numbers_after_second_failure():
    bad = {**GOOD, "headline": "Mobile payments collapsed to 12%."}
    result = narrative.generate(sheet(), {}, "en", FakeClient([bad, bad]))
    assert not result.verified and result.unverified == ["12%"]


def test_template_without_model_or_on_failure():
    no_model = narrative.generate(sheet(), {}, "en", None)
    assert no_model.mode == "template" and no_model.narrative.headline.startswith("mobile")
    failed = narrative.generate(sheet(), {}, "en", FakeClient([LLMError("down")]))
    assert failed.mode == "template" and failed.error == "down"


def test_prompt_contains_language_facts_and_data_boundary():
    messages = narrative.build_messages(sheet(), {"filters": "Period: Previous 12 weeks"}, "zh")
    assert "Simplified Chinese" in messages[0]["content"]
    assert "not instructions" in messages[0]["content"]
    payload = json.loads(messages[1]["content"].split("\n", 1)[1])
    assert payload["facts"][0]["id"] == "F1" and payload["filters"].startswith("Period")


def test_parse_narrative_tolerates_code_fences():
    parsed = narrative.parse_narrative("```json\n" + json.dumps(GOOD) + "\n```")
    assert parsed.headline == GOOD["headline"]


def test_chat_client_retries_without_optional_parameters():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((request.headers.get("x-session"), body))
        if "response_format" in body:
            return httpx.Response(400, json={"error": "response_format unsupported"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"headline": "ok"}'}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    cfg = LLMConfig(
        "https://llm.example/v1", "key", "m", reasoning_effort="none", session_header="x-session"
    )
    completion = ChatClient(cfg, transport=httpx.MockTransport(handler)).complete([])
    assert completion.content == '{"headline": "ok"}' and completion.prompt_tokens == 7
    assert seen[0][1]["reasoning_effort"] == "none" and "response_format" not in seen[1][1]
    assert seen[0][0] and seen[0][0] == seen[1][0]  # one session id per client


def test_chat_client_errors():
    def handler(request):
        return httpx.Response(500, text="boom")

    client = ChatClient(LLMConfig("https://x/v1", "k", "m"), transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError, match="500"):
        client.complete([])
