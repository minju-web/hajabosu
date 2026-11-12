"""입력 폴더(접수함)의 접수 원문을 일괄 처리해 하자대장 CSV로 저장한다.

사용: python run.py [입력폴더] [출력파일]
"""
import csv
import sys
from pathlib import Path

import ai
import rules

BASE = Path(__file__).resolve().parent
입력폴더 = BASE / "data" / "접수함"
출력파일 = BASE / "data" / "하자대장.csv"

열 = ["접수번호", "접수일", "원문파일", "위치", "공종", "하자내용", "긴급도", "조치기한",
      "공사번호", "시공업체", "준공일", "보증만료일", "보증판정", "책임구분", "상태", "비고"]
허용공종 = {"방수", "타일", "전기", "설비", "기계", "도장", "바닥재"}


def 점검(행: dict) -> list[str]:
    """AI 결과가 약속한 형식인지 검사하고, 어긋난 점을 돌려준다."""
    문제 = []
    if len(행["하자내용"]) > 40:
        문제.append(f"하자내용 {len(행['하자내용'])}자(40자 초과)")
    if not {x.strip() for x in 행["공종"].split("/")} <= 허용공종:
        문제.append(f"허용 밖 공종 {행['공종']!r}")
    return 문제


def main(입력=입력폴더, 출력=출력파일):
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

    # utf-8-sig: 엑셀에서 한글이 깨지지 않게 한다
    with open(출력, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=열)
        w.writeheader()
        w.writerows([{k: 행[k] for k in 열} for 행 in 행들])

    print(f"\n{len(행들)}건 저장 -> {출력}" + (f" (실패 {len(실패)}건)" if 실패 else ""))


if __name__ == "__main__":
    args = sys.argv[1:]
    main(*(Path(a) for a in args[:2]))
