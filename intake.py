"""접수 화면: 하자 접수를 입력해 DB(접수 테이블)에 저장한다.

실행: streamlit run intake.py --server.port 8502
저장만 한다. 하자대장으로 만드는 처리는 터미널에서 `python run.py`.
"""
from datetime import date

import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="하자 접수", page_icon=":material/edit_note:", layout="centered")

st.title("하자 접수")
st.caption("발견한 하자를 적어 주세요. 접수일은 발견일로 기록됩니다.")

with st.form("접수", clear_on_submit=True, border=True):
    발견일 = st.date_input("발견일", value=date.today(), max_value=date.today())
    c1, c2 = st.columns(2)
    접수자 = c1.text_input("접수자")
    부서 = c2.text_input("부서")
    위치 = st.text_input("위치", placeholder="예: 3층 패션관 남쪽 복도")
    내용 = st.text_area("하자 내용", placeholder="무엇이 어떻게 되어 있는지, 영업·고객 영향이 있으면 함께 적어 주세요.", height=140)
    제출 = st.form_submit_button("접수하기", type="primary", icon=":material/send:")

if 제출:
    빠짐 = [이름 for 이름, 값 in [("접수자", 접수자), ("위치", 위치), ("하자 내용", 내용)] if not 값.strip()]
    if 빠짐:
        st.error(f"{', '.join(빠짐)}을(를) 입력해 주세요.", icon=":material/error:")
    else:
        try:
            새id = db.접수_추가(발견일, 접수자.strip(), 부서.strip(), 위치.strip(), 내용.strip())
        except Exception as e:  # 연결 정보(비밀번호)는 db.py가 이미 지운 메시지만 나온다
            st.error(str(e), title="접수를 저장하지 못했습니다", icon=":material/error:")
        else:
            st.success(f"접수 {새id}번으로 저장했습니다. 하자대장에는 `python run.py`를 실행하면 올라갑니다.", icon=":material/check_circle:")

st.subheader("최근 접수")
try:
    최근 = db.접수_읽기(최근=10)
except Exception as e:
    st.error(str(e), title="접수 목록을 읽지 못했습니다", icon=":material/error:")
    st.stop()
if 최근:
    표 = pd.DataFrame(최근)[["id", "발견일", "접수자", "부서", "위치", "내용", "처리상태", "접수번호"]]
    st.dataframe(표.iloc[::-1], hide_index=True, alt="최근 접수 10건: 발견일, 위치, 내용, 처리상태")
else:
    st.caption("아직 접수가 없습니다.")
