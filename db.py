"""저장은 이 파일에서만 한다. 연결 정보는 .env의 DATABASE_URL (웹 배포는 Streamlit Secrets).

처음 실행하면 테이블 2개(접수, 하자대장)를 만들고 두 테이블 모두 RLS를 켠다.
비밀번호가 든 DATABASE_URL과 오류 속 비밀번호는 화면·로그에 내보내지 않는다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    Column, Date, DateTime, Integer, MetaData, String, Table, Text, CheckConstraint,
    create_engine, func, select, text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

load_dotenv(Path(__file__).resolve().parent / ".env")

# 하자대장 열 (data/하자대장.csv와 같다)
대장열 = ["접수번호", "접수일", "원문파일", "위치", "공종", "하자내용", "긴급도", "조치기한",
          "공사번호", "시공업체", "준공일", "보증만료일", "보증판정", "책임구분", "상태", "비고"]

metadata = MetaData()

접수 = Table(
    "접수", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("접수일시", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("발견일", Date),
    Column("접수자", Text),
    Column("부서", Text),
    Column("위치", Text),
    Column("내용", Text),
    Column("처리상태", String, nullable=False, server_default="미처리"),
    Column("접수번호", Text),
    CheckConstraint("처리상태 in ('미처리', '처리완료')", name="접수_처리상태_check"),
)

# CSV와 같은 값을 그대로 담기 위해 모두 문자열로 둔다 (날짜는 YYYY-MM-DD)
하자대장 = Table(
    "하자대장", metadata,
    *[Column(c, Text, primary_key=(c == "접수번호"), nullable=(c != "접수번호"), server_default=("" if c != "접수번호" else None))
      for c in 대장열],
)

_engine: Engine | None = None


class DBError(RuntimeError):
    """연결 정보(비밀번호)가 들어가지 않은 오류."""


def _url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DBError(".env에 DATABASE_URL이 없습니다.")
    if "[YOUR-PASSWORD]" in url:
        raise DBError("DATABASE_URL의 [YOUR-PASSWORD]를 DB 비밀번호로 바꿔 주세요.")
    # SQLAlchemy가 psycopg(3) 드라이버를 쓰도록 접두어를 맞춘다
    for 접두 in ("postgresql://", "postgres://"):
        if url.startswith(접두):
            return "postgresql+psycopg://" + url[len(접두):]
    return url


def _안전한_메시지(e: Exception) -> str:
    """오류 메시지에서 DATABASE_URL 전체와 비밀번호를 지운다."""
    msg = str(e)
    url = os.environ.get("DATABASE_URL", "")
    for 비밀 in filter(None, [url, _url_password(url)]):
        msg = msg.replace(비밀, "***")
    return msg


def _url_password(url: str) -> str:
    try:
        from sqlalchemy.engine import make_url
        return make_url(url).password or ""
    except Exception:
        return ""


def _초기화(engine: Engine) -> None:
    """테이블이 없으면 만들고, 두 테이블 모두 RLS를 켠다 (여러 번 실행해도 안전)."""
    metadata.create_all(engine)
    with engine.begin() as conn:
        for 이름 in ("접수", "하자대장"):
            conn.execute(text(f'ALTER TABLE "{이름}" ENABLE ROW LEVEL SECURITY'))


def 연결() -> Engine:
    """엔진을 돌려준다. 처음 한 번은 테이블 생성과 RLS 설정도 한다."""
    global _engine
    if _engine is None:
        try:
            engine = create_engine(_url(), pool_pre_ping=True)
            _초기화(engine)
        except DBError:
            raise
        except SQLAlchemyError as e:
            raise DBError(f"DB 연결 또는 초기화에 실패했습니다: {_안전한_메시지(e)}") from None
        _engine = engine
    return _engine


# ---------- 하자대장 ----------
def 대장_읽기() -> list[dict]:
    """하자대장 전체를 접수번호 순으로 돌려준다. (열은 CSV와 같다)"""
    with 연결().connect() as conn:
        rows = conn.execute(select(하자대장).order_by(하자대장.c.접수번호)).mappings().all()
    return [{c: (r[c] or "") for c in 대장열} for r in rows]


def 대장_저장(행들: list[dict]) -> int:
    """접수번호가 같으면 갱신하고 없으면 추가한다. 저장한 건수를 돌려준다."""
    if not 행들:
        return 0
    값들 = [{c: (행.get(c) or "") for c in 대장열} for 행 in 행들]
    stmt = pg_insert(하자대장).values(값들)
    stmt = stmt.on_conflict_do_update(
        index_elements=["접수번호"],
        set_={c: stmt.excluded[c] for c in 대장열 if c != "접수번호"},
    )
    with 연결().begin() as conn:
        conn.execute(stmt)
    return len(값들)


# ---------- 접수 (접수 화면 intake.py 입력) ----------
접수원문_접두 = "DB접수-"  # 하자대장의 원문파일 칸에 `DB접수-<id>`로 적는다


def 접수_추가(발견일, 접수자: str, 부서: str, 위치: str, 내용: str) -> int:
    """접수 1건을 미처리로 저장하고 id를 돌려준다."""
    with 연결().begin() as conn:
        return conn.execute(
            접수.insert().values(발견일=발견일, 접수자=접수자, 부서=부서, 위치=위치, 내용=내용).returning(접수.c.id)
        ).scalar_one()


def 접수_읽기(미처리만: bool = False, 최근: int | None = None) -> list[dict]:
    """접수 목록 (id 순). 최근=N이면 마지막 N건."""
    stmt = select(접수).order_by(접수.c.id)
    if 미처리만:
        stmt = stmt.where(접수.c.처리상태 == "미처리")
    with 연결().connect() as conn:
        rows = [dict(r) for r in conn.execute(stmt).mappings().all()]
    return rows[-최근:] if 최근 else rows


def 접수_원문(행: dict) -> str:
    """접수 1건을 AI가 읽을 원문 텍스트로 만든다 (위치는 접수자가 적은 그대로)."""
    return (
        f"발견일: {행['발견일']}\n접수자: {행['접수자'] or ''} ({행['부서'] or ''})\n"
        f"위치: {행['위치'] or ''}\n내용: {행['내용'] or ''}"
    )


def 접수_처리완료(id: int, 접수번호: str) -> None:
    with 연결().begin() as conn:
        conn.execute(접수.update().where(접수.c.id == id).values(접수번호=접수번호, 처리상태="처리완료"))


def 접수_하나(id: int) -> dict | None:
    with 연결().connect() as conn:
        r = conn.execute(select(접수).where(접수.c.id == id)).mappings().first()
    return dict(r) if r else None


# ---------- 확인용 ----------
def 건수() -> dict[str, int]:
    """테이블별 건수."""
    with 연결().connect() as conn:
        return {t.name: conn.execute(select(func.count()).select_from(t)).scalar_one() for t in (접수, 하자대장)}
