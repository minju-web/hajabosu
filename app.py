"""담당자 화면: 접수 원문이 하자대장이 되기까지의 과정을 단계별로 보여준다.

실행: streamlit run app.py
"""
from pathlib import Path

import pandas as pd
import streamlit as st

import db
import rules

BASE = Path(__file__).resolve().parent
접수함 = BASE / "data" / "접수함"
대장열 = ["접수번호", "접수일", "원문파일", "위치", "공종", "하자내용", "긴급도", "조치기한",
       "공사번호", "시공업체", "준공일", "보증만료일", "보증판정", "책임구분", "상태", "비고"]
AI칸 = ["접수일", "위치", "공종", "하자내용", "긴급도"]
표열 = ["접수번호", "위치", "공종", "하자내용", "긴급도", "조치기한", "보증판정", "책임구분", "상태", "비고"]
판정색 = {"보증내": "green", "보증만료": "orange", "확인필요": "red"}

st.set_page_config(page_title="하자보수 접수 처리", page_icon=":material/build:", layout="wide")


@st.cache_data(ttl="1m")
def 대장읽기() -> pd.DataFrame:
    return pd.DataFrame(rules.대장_읽기(), columns=대장열)


@st.cache_data
def 원문읽기(이름: str) -> str:
    if 이름.startswith(db.접수원문_접두):  # intake.py로 입력한 DB 접수
        r = db.접수_하나(int(이름[len(db.접수원문_접두):]))
        return db.접수_원문(r) if r else "(DB에서 접수를 찾지 못했습니다)"
    return (접수함 / 이름).read_text(encoding="utf-8-sig")


@st.cache_data
def 공사목록읽기() -> list[dict]:
    return rules.공사정보_읽기()


st.session_state.setdefault("live", {})  # 이 화면에서 AI를 다시 부른 결과 (저장하지 않음)

st.title("하자보수 접수 처리")
st.caption(
    "접수 원문이 하자대장이 되기까지: 원문 → :violet-badge[AI] 정리 → :blue-badge[코드] 계산 → 하자대장 → :orange-badge[사람] 확인"
)

try:
    대장 = 대장읽기()
except Exception as e:  # 연결 정보(비밀번호)는 db.py가 이미 지운 메시지만 나온다
    st.error(str(e), title="하자대장(DB)을 읽지 못했습니다", icon=":material/error:")
    st.stop()
if 대장.empty:
    st.warning("하자대장이 비어 있습니다. 터미널에서 `python run.py`를 먼저 실행하세요.", icon=":material/info:")
    st.stop()
공사목록 = 공사목록읽기()

# ---------- 요약 ----------
지표 = [
    ("전체 접수", len(대장)),
    ("긴급", int((대장["긴급도"] == "긴급").sum())),
    ("업체 요청 (보증내)", int((대장["보증판정"] == "보증내").sum())),
    ("자체보수 (보증만료)", int((대장["보증판정"] == "보증만료").sum())),
    ("확인필요", int((대장["보증판정"] == "확인필요").sum())),
]
for col, (이름, 값) in zip(st.columns(len(지표)), 지표):
    col.metric(이름, f"{값}건", border=True, height="stretch")

# ---------- 하자대장 ----------
st.subheader("하자대장")
st.caption("행을 선택하면 아래에 그 건이 처리된 과정이 나옵니다.")
event = st.dataframe(
    대장[표열],
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="대장표",
    alt="접수 7건의 하자대장: 위치, 공종, 긴급도, 조치기한, 보증판정",
)
선택 = event.selection.rows
행 = 대장.iloc[선택[0] if 선택 else 0]

st.divider()
st.subheader(f"{행['접수번호']} 처리 과정")

# ---------- 1·2단계: 원문 / AI ----------
c1, c2 = st.columns(2)

with c1.container(border=True):
    st.markdown("**1. 접수 원문** :gray-badge[입력]")
    st.caption(행["원문파일"])
    st.code(원문읽기(행["원문파일"]), language=None, wrap_lines=True)

with c2.container(border=True):
    st.markdown("**2. AI가 정리** :violet-badge[AI]")
    st.caption("원문에서 접수일·위치·공종·하자내용·긴급도를 뽑습니다. 의미 해석이 필요한 칸만 AI가 맡습니다.")
    if st.button("AI로 다시 정리", icon=":material/refresh:", key="ai다시"):
        import ai  # API 호출은 버튼을 눌렀을 때만 한다

        with st.spinner("Claude가 읽는 중..."):
            try:
                if 행["원문파일"].startswith(db.접수원문_접두):
                    결과 = ai.접수정리_텍스트(행["원문파일"], 원문읽기(행["원문파일"]))
                    결과["접수일"] = 행["접수일"]  # DB 접수는 발견일이 접수일
                else:
                    결과 = ai.접수정리(str(접수함 / 행["원문파일"]))
                st.session_state.live[행["원문파일"]] = 결과
            except Exception as e:
                st.error(str(e))
    live = st.session_state.live.get(행["원문파일"])
    값 = {k: (live[k] if live else 행[k]) for k in AI칸}
    표 = dict(값)
    if live:
        표["긴급도 근거"] = live["긴급도_근거"]
    st.table(표, border="horizontal")
    if live:
        다른 = [k for k in AI칸 if live[k] != 행[k]]
        if 다른:
            st.warning(f"저장된 하자대장과 다른 칸: {', '.join(다른)} (이 화면에서만 확인용, 저장하지 않음)", icon=":material/difference:")
        else:
            st.caption("다시 정리한 결과가 저장된 하자대장과 같습니다.")
    else:
        st.caption("긴급도 근거는 '다시 정리'를 누르면 나옵니다. (하자대장에는 저장하지 않는 칸)")

# ---------- 3단계: 코드 ----------
접수일, 위치, 공종, 긴급도 = 값["접수일"], 값["위치"], 값["공종"], 값["긴급도"]
기한 = rules.조치기한(긴급도, 접수일)
판정 = rules.판정(접수일, 위치, 공종, 공사목록)
후보 = rules.후보공사(위치, 공종, 공사목록)

with st.container(border=True):
    st.markdown("**3. 코드가 계산** :blue-badge[코드]")
    st.caption("번호·기한·보증 판정은 AI가 아니라 코드가 계산합니다. 접수일 기준이며 오늘 날짜는 쓰지 않습니다.")

    st.markdown(
        f"- **접수번호** `{행['접수번호']}`: `HJ-접수일-순번`, 같은 날 접수의 순번\n"
        f"- **조치기한** `{기한}`: {긴급도}은 접수일 + {rules.기한_일수[긴급도]}일"
    )

    st.markdown(f"- **공사 매칭**: 위치 `{위치}` + 공종 `{공종}`이 모두 같은 공사")
    if 후보:
        st.dataframe(
            pd.DataFrame(후보)[["공사번호", "공사명", "시공업체", "준공일", "하자보증기간(년)"]],
            hide_index=True,
            alt="위치와 공종이 일치하는 후보 공사",
        )
    else:
        st.caption("일치하는 공사가 없습니다.")

    if 판정["보증만료일"]:
        기호 = "이전(같은 날 포함)" if 판정["보증판정"] == "보증내" else "이후"
        st.markdown(
            f"- **보증 판정** :{판정색[판정['보증판정']]}-badge[{판정['보증판정']}]: "
            f"준공일 {판정['준공일']} + 보증기간 = 보증만료일 `{판정['보증만료일']}`, "
            f"접수일 {접수일}은 만료일 {기호} → 책임 **{판정['책임구분']}**"
        )
    else:
        if "/" in 공종:
            이유 = f"공종이 `{공종}`로 하나로 정해지지 않음"
        elif not 후보:
            이유 = "일치하는 공사가 없음"
        else:
            이유 = f"일치하는 공사가 {len(후보)}건"
        st.markdown(f"- **보증 판정** :red-badge[확인필요]: {이유}")
    if 판정["비고"]:
        st.markdown(f"- **비고**: {판정['비고']}")

# ---------- 4·5단계: 하자대장 / 사람 ----------
c4, c5 = st.columns(2)

with c4.container(border=True):
    st.markdown("**4. 하자대장에 기록**")
    st.caption("AI 칸과 코드 칸을 합친 16개 항목 한 줄입니다.")
    st.table({k: (v if v else "-") for k, v in 행.to_dict().items()}, border="horizontal")

with c5.container(border=True):
    st.markdown("**5. 사람이 확인** :orange-badge[사람]")
    if 행["보증판정"] == "확인필요":
        st.warning(
            f"현장을 보고 공종을 정해 주세요 (후보: {행['공종']}). 정한 뒤에 시공업체 요청 여부가 정해집니다.",
            title="담당자 확인 필요",
            icon=":material/priority_high:",
        )
    elif 행["책임구분"] == "시공업체":
        st.info(
            f"{행['시공업체']}에 보수 요청 공문을 보냅니다. 공문 내용을 확인하고 직접 발송하세요.",
            title="시공업체 요청 대상",
            icon=":material/mail:",
        )
    else:
        st.info("보증기간이 지나 시설관리팀이 직접 보수합니다. 보수 일정을 잡으세요.", title="자체보수", icon=":material/construction:")
    if 행["비고"].startswith("만료임박"):
        st.error("보증 만료가 30일 안으로 다가왔습니다. 만료 전에 꼭 요청해야 합니다.", title="만료임박", icon=":material/schedule:")
    if 행["긴급도"] == "긴급":
        st.caption(f"긴급 건입니다. 조치기한 {행['조치기한']}.")
