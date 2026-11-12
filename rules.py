"""번호·기한·판정 규칙. 기준은 data/업무설명_하자보수.md 이다. AI를 부르지 않는다."""
import csv
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
공사정보_경로 = BASE / "data" / "공사정보.csv"

# 4. 긴급도와 조치기한 (접수일 + N일)
기한_일수 = {"긴급": 1, "높음": 3, "보통": 7}
만료임박_일수 = 30


def _날짜(값) -> date:
    return 값 if isinstance(값, date) else date.fromisoformat(str(값))


# ---------- 접수번호 ----------
def 접수번호(접수일, 기존번호들=()) -> str:
    """HJ-접수일(YYYYMMDD)-순번(01부터). 같은 접수일의 기존 번호 다음 순번을 붙인다."""
    ymd = _날짜(접수일).strftime("%Y%m%d")
    앞 = f"HJ-{ymd}-"
    순번들 = [int(n[len(앞):]) for n in 기존번호들 if n.startswith(앞) and n[len(앞):].isdigit()]
    return f"{앞}{max(순번들, default=0) + 1:02d}"


# ---------- 조치기한 ----------
def 조치기한(긴급도: str, 접수일) -> str:
    """긴급 +1일, 높음 +3일, 보통 +7일. YYYY-MM-DD 문자열."""
    if 긴급도 not in 기한_일수:
        raise ValueError(f"알 수 없는 긴급도: {긴급도!r}")
    return (_날짜(접수일) + timedelta(days=기한_일수[긴급도])).isoformat()


# ---------- 공사정보 ----------
def 공사정보_읽기(경로=공사정보_경로) -> list[dict]:
    with open(경로, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ---------- 하자대장 읽기·저장 (실제 저장은 db.py) ----------
def 대장_읽기() -> list[dict]:
    import db  # 규칙 계산만 쓸 때는 DB 연결이 필요 없도록 필요할 때 불러온다
    return db.대장_읽기()


def 대장_저장(행들: list[dict]) -> int:
    import db
    return db.대장_저장(행들)


def 보증만료일(준공일, 보증년수) -> date | None:
    """준공일 + 하자보증기간(년). 윤일(2/29) 준공처럼 같은 날이 없으면 None."""
    d = _날짜(준공일)
    try:
        return d.replace(year=d.year + int(보증년수))
    except ValueError:
        return None


def 후보공사(위치: str, 공종: str, 공사목록) -> list[dict]:
    """위치가 같고 공종이 후보(`설비/타일`이면 둘 다) 중 하나인 공사들."""
    공종들 = [x.strip() for x in 공종.split("/") if x.strip()]
    return [c for c in 공사목록 if c["위치"] == 위치 and c["공종"] in 공종들]


# ---------- 보증 판정 ----------
def 판정(접수일, 위치: str, 공종: str, 공사목록) -> dict:
    """위치+공종이 모두 같은 공사를 찾아 보증을 판정한다. 기준일은 오늘이 아니라 접수일.

    반환 칸: 공사번호, 시공업체, 준공일, 보증만료일, 보증판정, 책임구분, 상태, 비고
    """
    접수 = _날짜(접수일)
    결과 = {
        "공사번호": "", "시공업체": "", "준공일": "", "보증만료일": "",
        "보증판정": "확인필요", "책임구분": "", "상태": "확인필요", "비고": "",
    }

    # 공종 미정(후보 병기)이면 한 건으로 정할 수 없다 -> 확인필요
    공종미정 = "/" in 공종 or not 공종.strip()
    후보 = 후보공사(위치, 공종, 공사목록)

    if 공종미정 or len(후보) != 1:
        # 확인필요 건도 후보 공사가 만료임박이면 비고에 함께 적는다
        임박 = []
        for c in 후보:
            만료 = 보증만료일(c["준공일"], c["하자보증기간(년)"])
            if 만료 and 0 <= (만료 - 접수).days <= 만료임박_일수:
                임박.append(f"{c['공사번호']} {c['시공업체']} {만료.isoformat()}")
        if 임박:
            결과["비고"] = "만료임박 (후보 " + ", ".join(임박) + ")"
        return 결과

    c = 후보[0]
    만료 = 보증만료일(c["준공일"], c["하자보증기간(년)"])
    결과.update(공사번호=c["공사번호"], 시공업체=c["시공업체"], 준공일=c["준공일"])
    if 만료 is None:
        결과["비고"] = "보증만료일 계산 불가(준공일 확인)"
        return 결과

    결과["보증만료일"] = 만료.isoformat()
    결과["상태"] = "판정완료"
    if 접수 <= 만료:  # 같은 날 포함
        결과["보증판정"], 결과["책임구분"] = "보증내", "시공업체"
        if (만료 - 접수).days <= 만료임박_일수:
            결과["비고"] = "만료임박"
    else:
        결과["보증판정"], 결과["책임구분"] = "보증만료", "자체보수"
    return 결과
