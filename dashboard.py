import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import os
import ast
import json

# 페이지 설정
st.set_page_config(
    page_title="NEMO 홍대 상권 분석 프로",
    page_icon="🏠",
    layout="wide"
)

# --- 7. 사용자 친화적 컬럼명 매핑 ---
COL_RENAME = {
    'title': '매물 제목',
    'businessLargeCodeName': '업종 대분류',
    'businessMiddleCodeName': '업종 소분류',
    'priceTypeName': '종류',
    'deposit': '보증금(만)',
    'monthlyRent': '월세(만)',
    'premium': '권리금(만)',
    'maintenanceFee': '관리비(만)',
    'floor': '층',
    'size': '면적(㎡)',
    'pyeong': '평수',
    'nearSubwayStation': '주변 전철역',
    'viewCount': '조회수',
    'favoriteCount': '찜횟수'
}

# 역 위치 매핑 (Phase 2 - 3. 지도 시각화를 위한 좌표)
STATION_COORDS = {
    "홍대입구역": [37.5574, 126.9242],
    "합정역": [37.5495, 126.9144],
    "망원역": [37.5560, 126.9100],
    "신촌역": [37.5551, 126.9369],
    "상수역": [37.5477, 126.9229],
    "연남동": [37.5615, 126.9245],
    "서교동": [37.5545, 126.9189],
    "동교동": [37.5583, 126.9262]
}

def parse_list(x):
    if not x or x == 'nan': return []
    try:
        return ast.literal_eval(x)
    except:
        return []

# 데이터 로드 및 전처리 (캐싱)
@st.cache_data
def load_data():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    db_path = os.path.join(project_root, "data", "nemostore.db")
    
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM stores", conn)
    conn.close()
    
    # 가격 단위 조정 (만원 단위로)
    price_cols = ['deposit', 'monthlyRent', 'maintenanceFee', 'premium']
    for col in price_cols:
        if col in df.columns:
            df[col] = df[col] / 10
            
    # 면적 평수 변환
    df['pyeong'] = (df['size'] / 3.3057).round(1)
    
    # 사진 데이터 파싱
    df['photo_list'] = df['smallPhotoUrls'].apply(parse_list)
    df['origin_photo_list'] = df['originPhotoUrls'].apply(parse_list)
    
    # 3. 지도용 좌표 할당 (간이 지오코딩)
    def get_lat_lon(station_str):
        if not station_str: return 37.5574, 126.9242
        for key, coords in STATION_COORDS.items():
            if key in station_str:
                return coords[0], coords[1]
        return 37.5574, 126.9242 # 기본: 홍대입구역
    
    # 좌표 컬럼 추가
    coords = df['nearSubwayStation'].apply(get_lat_lon)
    df['lat'] = [c[0] for c in coords]
    df['lon'] = [c[1] for c in coords]
    
    return df

# 데이터 로딩
try:
    df_raw = load_data()
except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()

# --- 4. 상대적 가치 평가 로직 (Phase 2 - Benchmarking) ---
# 업종별 평균 가격 미리 계산
biz_avg = df_raw.groupby('businessMiddleCodeName')[['monthlyRent', 'premium']].mean().rename(
    columns={'monthlyRent': 'avg_rent', 'premium': 'avg_premium'}
)

# --- 사이드바: 필터링 ---
st.sidebar.title("🔍 매물 맞춤 검색")

# 제목 검색
search_query = st.sidebar.text_input("매물명/지역 검색", "")

# 임대/매매
price_types = df_raw['priceTypeName'].unique().tolist()
selected_price_types = st.sidebar.multiselect("매물 종류", price_types, default=price_types)

# 층수 필터
floors = sorted(df_raw['floor'].unique().tolist())
selected_floors = st.sidebar.multiselect("층수 선택", floors, default=floors)

# 업종 필터
biz_types = sorted(df_raw['businessMiddleCodeName'].unique().tolist())
selected_biz = st.sidebar.multiselect("업종 분류", biz_types, default=[])

# 슬라이더
st.sidebar.markdown("---")
deposit_range = st.sidebar.slider("보증금(만)", 0, int(df_raw['deposit'].max()), (0, int(df_raw['deposit'].max())))
rent_range = st.sidebar.slider("월세(만)", 0, int(df_raw['monthlyRent'].max()), (0, int(df_raw['monthlyRent'].max())))
premium_range = st.sidebar.slider("권리금(만)", 0, int(df_raw['premium'].max()), (0, int(df_raw['premium'].max())))

# --- 데이터 필터링 ---
df_filtered = df_raw.copy()
if search_query: df_filtered = df_filtered[df_filtered['title'].str.contains(search_query, case=False, na=False)]
if selected_price_types: df_filtered = df_filtered[df_filtered['priceTypeName'].isin(selected_price_types)]
if selected_floors: df_filtered = df_filtered[df_filtered['floor'].isin(selected_floors)]
if selected_biz: df_filtered = df_filtered[df_filtered['businessMiddleCodeName'].isin(selected_biz)]

df_filtered = df_filtered[
    (df_filtered['deposit'].between(deposit_range[0], deposit_range[1])) &
    (df_filtered['monthlyRent'].between(rent_range[0], rent_range[1])) &
    (df_filtered['premium'].between(premium_range[0], premium_range[1]))
]

# --- 9. 대시보드 레이아웃 고도화 (Tabs) ---
tab_gallery, tab_map, tab_stats, tab_table = st.tabs(["🖼️ 갤러리 뷰", "🗺️ 지도 뷰", "📈 상권 통계", "📋 전체 목록"])

# --- 1. 갤러리 뷰 테마 (Phase 2) ---
with tab_gallery:
    st.subheader(f"🏠 검색 결과: {len(df_filtered)}건")
    
    # 8. 데이터 내보내기 버튼 (Phase 2)
    csv = df_filtered.rename(columns=COL_RENAME).to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 필터링된 결과 다운로드 (CSV)", csv, "nemostore_search.csv", "text/csv")
    
    cols = st.columns(4)
    for idx, row in df_filtered.iterrows():
        with cols[idx % 4]:
            img_url = row['photo_list'][0] if row['photo_list'] else "https://via.placeholder.com/300?text=No+Image"
            st.image(img_url, use_container_width=True)
            st.markdown(f"**{row['title'][:15]}...**")
            st.caption(f"{row['businessMiddleCodeName']} | {row['floor']}층 | {row['pyeong']}평")
            st.markdown(f"💰 **{row['deposit']}/{row['monthlyRent']}** (권리 {row['premium']})")
            
            # 2. 상세 정보 팝업 (Phase 2 - st.dialog 대용 버튼)
            if st.button("상세보기", key=f"btn_{row['id']}"):
                # 벤치마킹 계산
                avg_r = biz_avg.loc[row['businessMiddleCodeName'], 'avg_rent']
                diff_pct = ((row['monthlyRent'] - avg_r) / avg_r * 100) if avg_r > 0 else 0
                
                # 상세 페이지 모달 구성
                with st.expander(f"📌 {row['title']} 상세 정보", expanded=True):
                    ic1, ic2 = st.columns([1, 1])
                    with ic1:
                        st.image(row['origin_photo_list'] if row['origin_photo_list'] else img_url, use_container_width=True)
                    with ic2:
                        st.subheader("매물 가격 정보")
                        st.write(f"🏷️ **보증금**: {row['deposit']} 만원")
                        st.write(f"💸 **월세**: {row['monthlyRent']} 만원")
                        st.write(f"🎁 **권리금**: {row['premium']} 만원")
                        
                        # 4. 벤치마킹 지표 시각화
                        st.markdown("---")
                        st.write(f"⚖️ **상권 가격 진단 (동일 업종 {row['businessMiddleCodeName']} 기준)**")
                        if diff_pct < 0:
                            st.success(f"시장 평균 대비 **{abs(diff_pct):.1f}% 저렴**한 매물입니다!")
                        else:
                            st.warning(f"시장 평균 대비 **{diff_pct:.1f}% 높은** 가격입니다.")
                        
                        st.write(f"📍 **위치**: {row['nearSubwayStation']}")
                        st.write(f"🏢 **층수**: {row['floor']}층 / {row['groundFloor']}층")

# --- 3. 지도 뷰 (Phase 2) ---
with tab_map:
    st.subheader("🎯 매물 위치 및 밀집도")
    if len(df_filtered) > 0:
        st.map(df_filtered[['lat', 'lon']], zoom=13)
        st.info("💡 각 역 및 지역별 매물 분포를 시각화합니다. (기본 좌표 기준)")
    else:
        st.warning("표시할 매물이 없습니다.")

# --- 10. 통계 뷰 (기존 시각화 강화) ---
with tab_stats:
    st.subheader("📊 지역 상권 데이터 요약")
    
    # 상단 요약 지표
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("평균 임대료", f"{df_filtered['monthlyRent'].mean():.0f}만")
    m2.metric("최고가 월세", f"{df_filtered['monthlyRent'].max():.0f}만")
    m3.metric("평균 평수", f"{df_filtered['pyeong'].mean():.1f}평")
    m4.metric("무권리 비중", f"{(df_filtered['premium'] == 0).mean()*100:.1f}%")
    
    st.markdown("---")
    sc1, sc2 = st.columns(2)
    with sc1:
        # 업종 트리맵 (Phase 2 - 9. 트리맵 강화)
        fig_tree = px.treemap(
            df_filtered,
            path=[px.Constant("전체"), 'businessLargeCodeName', 'businessMiddleCodeName'],
            values='deposit',
            color='monthlyRent',
            color_continuous_scale='RdBu_r',
            title="업종 카테고리별 임대 규모",
            template="plotly_dark"
        )
        st.plotly_chart(fig_tree, use_container_width=True)
    
    with sc2:
        # 6. 층별 임대료 분석 (Phase 2)
        floor_analysis = df_filtered.groupby('floor')[['monthlyRent', 'pyeong']].mean().reset_index()
        floor_analysis['rent_per_pyeong'] = floor_analysis['monthlyRent'] / floor_analysis['pyeong']
        
        fig_floor = px.line(
            floor_analysis, x='floor', y='rent_per_pyeong', 
            markers=True, title="층별 평당 임대료 추이",
            labels={'rent_per_pyeong': '평당 월세(만)', 'floor': '층'},
            template="plotly_dark"
        )
        st.plotly_chart(fig_floor, use_container_width=True)

# --- 전체 목록 탭 ---
with tab_table:
    # 7. 사용자 친화적 용어 매핑 적용
    df_display = df_filtered.rename(columns=COL_RENAME)
    st.dataframe(df_display[list(COL_RENAME.values())], use_container_width=True, hide_index=True)

st.sidebar.caption("v2.0 Performance Optimized")
