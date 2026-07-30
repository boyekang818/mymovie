import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="박스오피스 대시보드", layout="wide")
st.title("🎬 어제의 박스오피스")

# 비밀 금고에서 인증키 꺼내기 (코드에는 키를 적지 않는다)
KOBIS_KEY = st.secrets["KOBIS_KEY"]

BASE_DAILY_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
BASE_WEEKLY_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchWeeklyBoxOfficeList.json"


@st.cache_data(ttl=60 * 60)
def fetch_daily(target_dt: str):
    res = requests.get(BASE_DAILY_URL, params={"key": KOBIS_KEY, "targetDt": target_dt}, timeout=10)
    res.raise_for_status()
    return res.json()


@st.cache_data(ttl=60 * 60 * 24)
def fetch_weekly(target_dt: str, week_gb: str = "0"):
    res = requests.get(
        BASE_WEEKLY_URL,
        params={"key": KOBIS_KEY, "targetDt": target_dt, "weekGb": week_gb},
        timeout=10,
    )
    res.raise_for_status()
    return res.json()


def get_season(month: int) -> str:
    if month in (3, 4, 5):
        return "🌸 봄"
    elif month in (6, 7, 8):
        return "🌞 여름"
    elif month in (9, 10, 11):
        return "🍂 가을"
    else:
        return "❄️ 겨울"


# ── 한국 시간 기준 어제 날짜 ──────────────────────────────
yesterday = datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")
st.caption(f"조회 기준일(어제): {yesterday.strftime('%Y-%m-%d')}")

data = fetch_daily(target_dt)

if "faultInfo" in data:
    st.error("인증키가 올바르지 않습니다. 금고(Secrets)의 KOBIS_KEY를 확인해 주세요.")
    st.stop()

box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
if not box_list:
    st.warning("그날 자료가 없습니다. 날짜를 하루 더 앞으로 옮겨 보세요.")
    st.stop()

df = pd.DataFrame(box_list)

numeric_cols = [
    "rank", "rankInten", "audiCnt", "audiInten", "audiAcc",
    "scrnCnt", "showCnt", "salesAmt", "salesInten",
    "salesAcc", "salesShare", "salesChange", "audiChange",
]
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")


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
df["티켓단가"] = (df["salesAmt"] / df["audiCnt"]).replace([float("inf")], 0).fillna(0)

# ── 1위 영화 지표 카드 ────────────────────────────────────
top = df.sort_values("rank").iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("어제 1위", top["movieNm"])
c2.metric("어제 관객수", f"{top['audiCnt']:,}명", delta=f"{int(top['audiInten']):,}명")
c3.metric("어제 매출액", f"{top['salesAmt']:,}원", delta=f"{top['salesChange']:.1f}%")
c4.metric("누적 관객", f"{top['audiAcc']:,}명")

# ── 표 ────────────────────────────────────────────────────
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
        "매출점유율(%)": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
    },
    hide_index=True,
    use_container_width=True,
)

st.subheader("📈 관객수 상위 5편")
top5 = table.sort_values("관객수", ascending=False).head(5)
st.bar_chart(top5.set_index("영화명")["관객수"])

st.subheader("🥧 매출 점유율")
share_df = df[["movieNm", "salesShare"]].sort_values("salesShare", ascending=False)
st.plotly_chart(
    {
        "data": [{"labels": share_df["movieNm"], "values": share_df["salesShare"], "type": "pie", "hole": 0.4}],
        "layout": {"margin": dict(t=10, b=10, l=10, r=10)},
    },
    use_container_width=True,
)

# ── 오늘의 인사이트 (추가 API 호출 없이 바로 계산) ───────────
st.divider()
st.subheader("💡 오늘의 인사이트")

i1, i2, i3 = st.columns(3)

priciest = df.loc[df["티켓단가"].idxmax()]
i1.metric("가장 비싼 평균 티켓값", priciest["movieNm"], f"{priciest['티켓단가']:,.0f}원")

top1_share = top["salesShare"]
if top1_share >= 50:
    dominance_msg = "완전 독주 🏆"
elif top1_share >= 30:
    dominance_msg = "강세 📈"
else:
    dominance_msg = "혼전 양상 🤼"
i2.metric("1위 매출 독과점 지수", f"{top1_share:.1f}%", dominance_msg)

new_movies = df[df["rankOldAndNew"] == "NEW"]
i3.metric("오늘의 신규 진입작", f"{len(new_movies)}편")
if len(new_movies) > 0:
    st.caption("🆕 " + ", ".join(new_movies.sort_values("rank")["movieNm"].tolist()))

# ── 영화별 상세보기 ───────────────────────────────────────
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
            st.write(f"**평균 티켓 단가**: {row['티켓단가']:,.0f}원")
            if row["scrnCnt"] > 0:
                st.write(f"**스크린당 평균 상영횟수**: {row['showCnt'] / row['scrnCnt']:.1f}회")

# ── 계절별 극장가 트렌드 (버튼으로 실행, 무거운 호출) ─────────
st.divider()
st.subheader("🍂 계절별 극장가 트렌드")
st.caption("최근 N개월간 매월 둘째 주 주간 박스오피스를 표본으로 계절별 관객 동향을 살펴봅니다.")

months_back = st.select_slider("조회 범위", options=[6, 12, 18, 24], value=12)
run = st.button("계절별 트렌드 불러오기")

if run:
    records = []
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    with st.spinner(f"최근 {months_back}개월 데이터를 불러오는 중..."):
        for i in range(months_back):
            sample_date = now - relativedelta(months=i)
            sample_date = sample_date.replace(day=15)
            dt_str = sample_date.strftime("%Y%m%d")
            try:
                wk_data = fetch_weekly(dt_str, week_gb="0")
                wk_list = wk_data.get("boxOfficeResult", {}).get("weeklyBoxOfficeList", [])
            except Exception:
                wk_list = []
            if not wk_list:
                continue
            wk_df = pd.DataFrame(wk_list)
            wk_df["audiCnt"] = pd.to_numeric(wk_df["audiCnt"], errors="coerce")
            total_audi = wk_df["audiCnt"].sum()
            top_movie = wk_df.sort_values("rank").iloc[0]["movieNm"] if "rank" in wk_df.columns else wk_df.iloc[0]["movieNm"]
            records.append({
                "연월": sample_date.strftime("%Y-%m"),
                "월": sample_date.month,
                "계절": get_season(sample_date.month),
                "표본주간_관객수": total_audi,
                "1위영화": top_movie,
            })

    if not records:
        st.warning("데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
    else:
        trend_df = pd.DataFrame(records).sort_values("연월")

        st.markdown("**월별 표본주간 관객수 추이**")
        st.line_chart(trend_df.set_index("연월")["표본주간_관객수"])

        season_avg = (
            trend_df.groupby("계절")["표본주간_관객수"]
            .mean()
            .reindex(["🌸 봄", "🌞 여름", "🍂 가을", "❄️ 겨울"])
            .dropna()
        )

        st.markdown("**계절별 평균 표본주간 관객수**")
        st.bar_chart(season_avg)

        best_season = season_avg.idxmax()
        worst_season = season_avg.idxmin()
        st.success(
            f"조사 기간({months_back}개월) 동안 극장가가 가장 붐빈 계절은 **{best_season}**, "
            f"가장 한산했던 계절은 **{worst_season}**이었어요."
        )

        with st.expander("월별 상세 표본 데이터 보기"):
            st.dataframe(
                trend_df[["연월", "계절", "1위영화", "표본주간_관객수"]],
                hide_index=True,
                use_container_width=True,
            )
