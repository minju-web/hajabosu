"""입력 폴더(접수함)의 접수 원문과 DB의 미처리 접수를 일괄 처리해 하자대장(DB)에 저장한다.

사용: python run.py [입력폴더]
DB 접수(intake.py 입력)는 발견일을 접수일로 쓰고, 처리하면 접수의 처리상태를 처리완료로 바꾼다.
접수번호가 같은 건은 갱신하고 새 건은 추가한다. (DB 저장은 rules.대장_저장 -> db.py)
"""
import sys
from pathlib import Path

import ai
import rules

BASE = Path(__file__).resolve().parent
입력폴더 = BASE / "data" / "접수함"

허용공종 = {"방수", "타일", "전기", "설비", "기계", "도장", "바닥재"}


def 점검(행: dict) -> list[str]:
    """AI 결과가 약속한 형식인지 검사하고, 어긋난 점을 돌려준다."""
    문제 = []
    if len(행["하자내용"]) > 40:
        문제.append(f"하자내용 {len(행['하자내용'])}자(40자 초과)")
    if not {x.strip() for x in 행["공종"].split("/")} <= 허용공종:
        문제.append(f"허용 밖 공종 {행['공종']!r}")
    return 문제


def main(입력=입력폴더):
    공사목록 = rules.공사정보_읽기()
    파일들 = sorted(Path(입력).glob("*.txt"))
    행들, 번호들, 실패 = [], [], []

    for p in 파일들:
        try:
            a = ai.접수정리(str(p))
        except Exception as e:  # 한 건이 실패해도 나머지는 계속 처리한다
            실패.append((p.name, str(e)))
            print(f"[실패] {p.name}: {e}")
            continue

        번호 = rules.접수번호(a["접수일"], 번호들)
        번호들.append(번호)
        판정 = rules.판정(a["접수일"], a["위치"], a["공종"], 공사목록)
        행 = {
            "접수번호": 번호, "접수일": a["접수일"], "원문파일": p.name,
            "위치": a["위치"], "공종": a["공종"], "하자내용": a["하자내용"],
            "긴급도": a["긴급도"], "조치기한": rules.조치기한(a["긴급도"], a["접수일"]),
            **판정,
        }
        for 문제 in 점검(행):
            print(f"[주의] {번호}: {문제}")
        행들.append(행)
        print(f"[완료] {번호} {a['위치']} {a['공종']} {a['긴급도']} -> {판정['보증판정']}")

    # DB 접수 (intake.py로 입력한 미처리 건): 접수일은 AI가 아니라 발견일을 쓴다
    import db

    대기 = db.접수_읽기(미처리만=True)
    if 대기:
        # 이미 쓴 번호(대장 + 접수)와 겹치지 않게 이어서 붙인다
        쓴번호 = list(번호들) + [r["접수번호"] for r in rules.대장_읽기()] + [
            r["접수번호"] for r in db.접수_읽기() if r["접수번호"]
        ]
        완료 = []  # (접수 id, 접수번호) — 대장 저장이 끝난 뒤에만 처리완료로 바꾼다
        for r in 대기:
            이름 = f"{db.접수원문_접두}{r['id']}"
            if not r["발견일"]:
                실패.append((이름, "발견일이 없습니다"))
                print(f"[실패] {이름}: 발견일이 없습니다")
                continue
            try:
                a = ai.접수정리_텍스트(이름, db.접수_원문(r))
            except Exception as e:
                실패.append((이름, str(e)))
                print(f"[실패] {이름}: {e}")
                continue

            접수일 = r["발견일"].isoformat()
            번호 = rules.접수번호(접수일, 쓴번호)
            쓴번호.append(번호)
            판정 = rules.판정(접수일, a["위치"], a["공종"], 공사목록)
            행 = {
                "접수번호": 번호, "접수일": 접수일, "원문파일": 이름,
                "위치": a["위치"], "공종": a["공종"], "하자내용": a["하자내용"],
                "긴급도": a["긴급도"], "조치기한": rules.조치기한(a["긴급도"], 접수일),
                **판정,
            }
            for 문제 in 점검(행):
                print(f"[주의] {번호}: {문제}")
            행들.append(행)
            완료.append((r["id"], 번호))
            print(f"[완료] {번호} (접수 {r['id']}번) {a['위치']} {a['공종']} {a['긴급도']} -> {판정['보증판정']}")
    else:
        완료 = []

    저장 = rules.대장_저장(행들)
    for id, 번호 in 완료:
        db.접수_처리완료(id, 번호)
    print(f"\n{저장}건 저장 -> 하자대장(DB)" + (f" (실패 {len(실패)}건)" if 실패 else ""))
    if 완료:
        print(f"DB 접수 {len(완료)}건을 처리완료로 바꿨습니다.")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(*(Path(a) for a in args[:1]))
