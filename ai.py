"""AI 호출은 이 파일에서만 한다. 키와 모델은 .env에서 읽는다.

.env 항목: ANTHROPIC_API_KEY, MODEL
"""
import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

# 접수정리 결과의 칸 이름과 형식 (지침/접수정리.md의 출력 형식과 같다)
접수정리_스키마 = {
    "type": "object",
    "properties": {
        "원문파일": {"type": "string"},
        "접수일": {"type": "string"},
        "위치": {"type": "string"},
        "공종": {"type": "string"},
        "하자내용": {"type": "string"},
        "긴급도": {"type": "string", "enum": ["긴급", "높음", "보통"]},
        "긴급도_근거": {"type": "string"},
    },
    "required": ["원문파일", "접수일", "위치", "공종", "하자내용", "긴급도", "긴급도_근거"],
    "additionalProperties": False,
}


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(".env에 ANTHROPIC_API_KEY가 없습니다.")
    return anthropic.Anthropic()


def _model() -> str:
    model = os.environ.get("MODEL")
    if not model:
        raise RuntimeError(".env에 MODEL이 없습니다.")
    return model


def 호출(지침파일: str, 입력: str, 스키마: dict) -> dict:
    """지침/ 폴더의 지침 파일을 시스템 프롬프트로 주고, 스키마에 맞는 JSON(dict)을 받는다."""
    지침 = (BASE / "지침" / 지침파일).read_text(encoding="utf-8")
    try:
        response = _client().messages.create(
            model=_model(),
            max_tokens=16000,
            system=지침,
            messages=[{"role": "user", "content": 입력}],
            output_config={"format": {"type": "json_schema", "schema": 스키마}},
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("API 키가 올바르지 않습니다. .env의 ANTHROPIC_API_KEY를 확인하세요.")
    except anthropic.RateLimitError:
        raise RuntimeError("요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
    except anthropic.APIConnectionError:
        raise RuntimeError("네트워크에 연결할 수 없습니다.")

    if response.stop_reason == "refusal":
        raise RuntimeError("AI가 응답을 거절했습니다.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("AI 응답이 길이 제한에서 잘렸습니다.")

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def 접수정리(원문파일: str) -> dict:
    """접수함의 원문 1건을 읽어 접수일·위치·공종·하자내용·긴급도를 JSON(dict)으로 돌려준다."""
    path = Path(원문파일)
    원문 = path.read_text(encoding="utf-8-sig")
    return 접수정리_텍스트(path.name, 원문)


def 접수정리_텍스트(이름: str, 원문: str) -> dict:
    """파일이 아닌 원문 텍스트(접수 화면에서 입력한 건)를 같은 지침으로 정리한다."""
    입력 = f"원문 파일명: {이름}\n\n[원문]\n{원문}"
    return 호출("접수정리.md", 입력, 접수정리_스키마)
