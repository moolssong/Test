import streamlit as st
import requests
import pandas as pd
import io
import re

# 페이지 설정
st.set_page_config(page_title="브이월드 개별공시지가 일괄 조회기", page_icon="🏰", layout="wide")

st.title("🏰 브이월드 개별공시지가 자동 일괄 조회 앱")
st.write("주소 목록을 복사·붙여넣기 하시면, PNU 자동 추출 및 브이월드 개별공시지가 조회가 이루어집니다. 🍰")

col1, col2 = st.columns([2, 1])
with col1:
    vworld_key = st.text_input(
        "🔑 브이월드(V-World) API 인증키",
        type="password",
        placeholder="여기에 API 키를 입력하세요"
    )
with col2:
    std_year = st.text_input(
        "📅 기준연도",
        value="2024",
        placeholder="예: 2024"
    )

st.markdown("### 📋 주소 목록 입력")
st.info("💡 **입력 팁:** 엑셀이나 메모장에서 주소와 번지가 포함된 텍스트를 복사해서 아래 칸에 그대로 붙여넣어 주세요. (예: `울산광역시 울주군 삼남읍 가천리 산23`)")

input_text = st.text_area(
    "주소를 줄바꿈 단위로 입력하세요",
    height=200,
    placeholder="울산광역시 울주군 삼남읍 가천리 산23\n경기도 가평군 가평읍 대곡리 568-9"
)

# PNU 생성 및 공시지가 조회 함수
def get_land_price_from_address(address_line, api_key, year):
    # 1. 산번지 여부 파악 ("산"이 포함되면 구분코드 '2', 아니면 '1')
    has_mountain = "산" in address_line
    lot_division = "2" if has_mountain else "1"
    
    # 2. 번지 추출
    match = re.search(r'산?\s*([0-9\-]+)', address_line)
    raw_bunji = match.group(1) if match else "0"
    
    if "-" in raw_bunji:
        parts = raw_bunji.split("-")
        bonbun = parts[0].zfill(4)
        bubun = parts[1].zfill(4)
    else:
        bonbun = raw_bunji.zfill(4)
        bubun = "0000"
        
    # 3. 법정동 코드 획득을 위한 주소 검색 API 호출
    geo_url = "https://api.vworld.kr/req/search"
    geo_params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "crs": "EPSG:4326",
        "size": 1,
        "page": 1,
        "query": address_line,
        "type": "address",
        "category": "parcel",
        "format": "json",
        "key": api_key
    }
    
    bjd_code = "4824033000" # 기본 fallback 코드
    try:
        resp = requests.get(geo_url, params=geo_params, timeout=5)
        data = resp.json()
        if data.get("response", {}).get("status") == "OK":
            items = data["response"]["result"]["items"]
            if items:
                api_pnu = items[0].get("id", "")
                if len(api_pnu) >= 10:
                    bjd_code = api_pnu[:10]
    except Exception:
        pass
        
    # 최종 19자리 PNU 조합
    constructed_pnu = f"{bjd_code}{lot_division}{bonbun}{bubun}"
    
    # 4. 개별공시지가 속성 API 호출 (정확한 API 규격 및 stdrYear 파라미터 적용)
    price_val = "지가 조회 실패"
    status_msg = "성공"
    
    try:
        price_url = "https://api.vworld.kr/ned/data/getIndvdLandPriceAttr"
        price_params = {
            "key": api_key,
            "domain": "wrwkpsgunvbdyepgnksjzp.streamlit.app",
            "format": "json",
            "stdrYear": year,   # <-- 수정된 공식 파라미터 이름 (stdrYear)
            "pnu": constructed_pnu
        }
        price_resp = requests.get(price_url, params=price_params, timeout=5)
        
        try:
            price_json = price_resp.json()
            fields = price_json.get("indvdLandPrices", {}).get("field", [])
            if fields:
                price_val = fields[0].get("indvdLandPrice", "정보없음")
            else:
                price_val = "해당연도 지가데이터 없음"
                status_msg = "데이터 없음"
        except Exception:
            status_msg = f"API 응답 형식 오류 (내용: {price_resp.text[:50]})"
            
    except Exception as e:
        status_msg = f"에러: {str(e)}"
        
    return {
        "산번지여부": "산번지 (구분: 2)" if has_mountain else "일반번지 (구분: 1)",
        "생성된PNU": constructed_pnu,
        "공시지가": price_val,
        "상태": status_msg
    }

if st.button("🚀 PNU 생성 및 공시지가 폭풍 조회 시작!", type="primary"):
    if not vworld_key.strip():
        st.warning("⚠️ 브이월드 API 인증키를 먼저 입력해 주세요!")
    elif not input_text.strip():
        st.warning("⚠️ 조회할 주소를 하나 이상 입력해 주세요!")
    else:
        lines = [line.strip() for line in input_text.split("\n") if line.strip()]

        results_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        total_count = len(lines)

        for i, line in enumerate(lines):
            status_text.text(f"⏳ 조회 중... ({i+1}/{total_count}): {line}")
            
            res = get_land_price_from_address(line, vworld_key, std_year)
            
            results_data.append({
                "입력주소": line,
                "기준연도": std_year,
                "지번구분": res["산번지여부"],
                "생성된 19자리 PNU": res["생성된PNU"],
                "공시지가(원/㎡)": res["공시지가"],
                "조회상태": res["상태"]
            })

            progress_bar.progress((i + 1) / total_count)

        status_text.text("✨ 모든 주소 조회 완료!")
        progress_bar.empty()

        df_result = pd.DataFrame(results_data)

        st.markdown("### 📊 조회 결과 미리보기")
        st.dataframe(df_result, use_container_width=True)

        # 엑셀 파일 다운로드 생성
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_result.to_excel(writer, index=False, sheet_name='공시지가조회결과')
        excel_data = output.getvalue()

        st.download_button(
            label="📥 결과 엑셀 파일로 다운로드하기",
            data=excel_data,
            file_name="land_price_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
        )
