import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="박스오피스 대시보드", layout="wide")
st.title("🎬 어제의 박스오피스")

# 비밀 금고에서 인증키 꺼내기 (코드에는 키를 적지 않는다)
KOBIS_KEY = st.secrets["KOBIS_KEY"]

# 한국 시간 기준 어제 날짜를 여덟 자리로 (배포 서버 시계는 외국 기준일 수 있다)
yesterday = datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")
st.caption(f"조회 기준일(어제): {yesterday.strftime('%Y-%m-%d')}")

url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
res = requests.get(url, params={"key": KOBIS_KEY, "targetDt": target_dt}, timeout=10)

if res.status_code != 200:
    st.error(f"요청이 실패했습니다 (상태코드: {res.status_code})")
    st.stop()

data = res.json()

# KOBIS는 키가 틀려도 상태코드 200을 준다. 대신 faultInfo 상자가 온다.
if "faultInfo" in data:
    st.error("인증키가 올바르지 않습니다. 금고(Secrets)의 KOBIS_KEY를 확인해 주세요.")
    st.stop()

box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
if not box_list:
    st.warning("그날 자료가 없습니다. 날짜를 하루 더 앞으로 옮겨 보세요.")
    st.stop()

df = pd.DataFrame(box_list)

# 글자로 온 숫자들을 진짜 숫자로 바꾸기 (매출/증감 필드까지 확장)
numeric_cols = [
    "rank", "rankInten", "audiCnt", "audiInten", "audiAcc",
    "scrnCnt", "showCnt", "salesAmt", "salesInten",
    "salesAcc", "salesShare", "salesChange", "audiChange",
]
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# 순위 변동을 화살표 문자열로 바꿔주는 도우미
def rank_change_label(row):
    if row["rankOldAndNew"] == "NEW":
        return "🆕 신규"
    inten = row["rankInten"]
    if inten > 0:
        return f"🔺{int(inten)}"
    elif inten < 0:
        return f"🔻{int(abs(inten))}"
    else:
        return "➖ 0"

df["순위변동"] = df.apply(rank_change_label, axis=1)

# 1위 영화 지표 카드 네 장 (매출 카드 추가)
top = df.sort_values("rank").iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("어제 1위", top["movieNm"])
c2.metric("어제 관객수", f"{top['audiCnt']:,}명", delta=f"{int(top['audiInten']):,}명")
c3.metric("어제 매출액", f"{top['salesAmt']:,}원", delta=f"{top['salesChange']:.1f}%")
c4.metric("누적 관객", f"{top['audiAcc']:,}명")

# 표를 한국어 열 이름으로 정리 (매출/점유율 열 추가)
table = df[[
    "rank", "순위변동", "movieNm", "openDt",
    "audiCnt", "audiAcc", "salesAmt", "salesShare", "scrnCnt",
]].copy()
table.columns = [
    "순위", "변동", "영화명", "개봉일",
    "관객수", "누적관객", "매출액", "매출점유율(%)", "스크린수",
]
table = table.sort_values("순위").reset_index(drop=True)

st.subheader("📋 박스오피스 TOP 10")
st.dataframe(
    table,
    column_config={
        "관객수": st.column_config.NumberColumn(format="%d 명"),
        "누적관객": st.column_config.NumberColumn(format="%d 명"),
        "매출액": st.column_config.NumberColumn(format="%d 원"),
        "매출점유율(%)": st.column_config.ProgressColumn(
            format="%.1f%%", min_value=0, max_value=100
        ),
    },
    hide_index=True,
    use_container_width=True,
)

# 관객수 상위 5편 막대그래프
st.subheader("📈 관객수 상위 5편")
top5 = table.sort_values("관객수", ascending=False).head(5)
st.bar_chart(top5.set_index("영화명")["관객수"])

# 매출 점유율 파이차트
st.subheader("🥧 매출 점유율")
share_df = df[["movieNm", "salesShare"]].sort_values("salesShare", ascending=False)
st.plotly_chart(
    {
        "data": [{
            "labels": share_df["movieNm"],
            "values": share_df["salesShare"],
            "type": "pie",
            "hole": 0.4,
        }],
        "layout": {"margin": dict(t=10, b=10, l=10, r=10)},
    },
    use_container_width=True,
)

# 영화별 상세 정보 (펼쳐보기)
st.subheader("🔍 영화별 상세보기")
for _, row in df.sort_values("rank").iterrows():
    badge = " 🆕" if row["rankOldAndNew"] == "NEW" else ""
    with st.expander(f"{int(row['rank'])}위 · {row['movieNm']}{badge}"):
        d1, d2 = st.columns(2)
        with d1:
            st.write(f"**개봉일**: {row['openDt']}")
            st.write(f"**당일 관객수**: {row['audiCnt']:,}명 ({row['audiChange']:+.1f}%)")
            st.write(f"**누적 관객수**: {row['audiAcc']:,}명")
            st.write(f"**스크린수**: {int(row['scrnCnt']):,}개")
            st.write(f"**상영횟수**: {int(row['showCnt']):,}회")
        with d2:
            st.write(f"**당일 매출액**: {row['salesAmt']:,}원 ({row['salesChange']:+.1f}%)")
            st.write(f"**누적 매출액**: {row['salesAcc']:,}원")
            st.write(f"**매출 점유율**: {row['salesShare']:.1f}%")
            if row["scrnCnt"] > 0:
                avg_show = row["showCnt"] / row["scrnCnt"]
                st.write(f"**스크린당 평균 상영횟수**: {avg_show:.1f}회")
