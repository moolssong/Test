import streamlit as st
import requests
import pandas as pd
import io
import re

# 페이지 설정
st.set_page_config(page_title="브이월드 개별공시지가 및 PNU 검증기", page_icon="🏰", layout="wide")

st.title("🏰 주소-PNU 자동 생성 및 공시지가 조회 앱")
st.write("주소 목록을 붙여넣으시면, **직접 파싱하여 생성한 PNU**와 **브이월드 API 결과**를 나란히 비교하고 공시지가를 조회하여 엑셀로 저장해 드립니다. 🍰")

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
        value="2026",
        placeholder="예: 2026"
    )

st.markdown("### 📋 주소 목록 입력")
st.info("💡 **입력 팁:** 엑셀이나 메모장에서 주소와 번지가 포함된 텍스트를 복사해서 아래 칸에 그대로 붙여넣어 주세요. (예: `울산광역시 울주군 삼남읍 가천리 산23`)")

input_text = st.text_area(
    "주소를 줄바꿈 단위로 입력하세요",
    height=200,
    placeholder="울산광역시 울주군 삼남읍 가천리 산23\n경기도 가평군 가평읍 대곡리 568-9"
)

# 1. 주소를 분석하여 자체적으로 PNU 코드 구조를 추출/생성하는 함수
def generate_pnu_from_address(address_line, api_key):
    geo_url = "https://api.vworld.kr/req/search"
    params = {
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
    
    # 산번지 여부 판단 (산이 포함되어 있으면 구분코드 2, 아니면 1)
    has_mountain = "산" in address_line
    lot_division = "2" if has_mountain else "1"
    
    # 번지 숫자 추출
    match = re.search(r'산?\s*([0-9\-]+)', address_line)
    raw_bunji = match.group(1) if match else "0"
    
    # 본번, 부번 분리 (예: 568-9 -> 본번 568, 부번 9)
    if "-" in raw_bunji:
        parts = raw_bunji.split("-")
        bonbun = parts[0].zfill(4)
        bubun = parts[1].zfill(4)
    else:
        bonbun = raw_bunji.zfill(4)
        bubun = "0000"
        
    try:
        response = requests.get(geo_url, params=params, timeout=5)
        res_data = response.json()
        
        if res_data.get("response", {}).get("status") == "OK":
            items = res_data["response"]["result"]["items"]
            if items:
                item = items[0]
                api_pnu = item.get("id", "") # 브이월드가 반환한 PNU (19자리)
                
                if len(api_pnu) >= 10:
                    bjd_code = api_pnu[:10]
                    my_generated_pnu = f"{bjd_code}{lot_division}{bonbun}{bubun}"
                else:
                    my_generated_pnu = f"추출불가{lot_division}{bonbun}{bubun}"
                    
                return {
                    "api_pnu": api_pnu,
                    "my_pnu": my_generated_pnu,
                    "status": "성공"
                }
        return {
            "api_pnu": "검색실패",
            "my_pnu": f"파생불가{lot_division}{bonbun}{bubun}",
            "status": "주소 검색 결과 없음"
        }
    except Exception as e:
        return {
            "api_pnu": "에러",
            "my_pnu": "에러",
            "status": f"오류: {str(e)}"
        }

# 2. 공시지가 조회 함수
def get_land_price(api_key, year, pnu_code):
    try:
        price_url = "https://api.vworld.kr/ned/data/getIndvdLandPriceAttr"
        price_params = {
            "key": api_key,
            "domain": "wrwkpsgunvbdyepgnksjzp.streamlit.app",
            "format": "json",
            "stdYear": year,
            "pnu": pnu_code
        }
        price_resp = requests.get(price_url, params=price_params, timeout=5)
        price_json = price_resp.json()
        
        fields = price_json.get("indvdLandPrices", {}).get("field", [])
        if fields:
            return fields[0].get("indvdLandPrice", "정보없음")
        else:
            return "지가데이터없음"
    except Exception:
        return "지가 조회 실패"

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
            status_text.text(f"⏳ 처리 중... ({i+1}/{total_count}): {line}")
            
            pnu_info = generate_pnu_from_address(line, vworld_key)
            target_pnu = pnu_info["my_pnu"] if len(pnu_info["my_pnu"]) == 19 else pnu_info["api_pnu"]
            land_price = get_land_price(vworld_key, std_year, target_pnu)
            
            has_mountain = "산" in line
            
            results_data.append({
                "입력주소": line,
                "기준연도": std_year,
                "산번지여부": "산 (구분:2)" if has_mountain else "일반 (구분:1)",
                "내가 생성한 PNU": pnu_info["my_pnu"],
                "API 반환 PNU": pnu_info["api_pnu"],
                "공시지가(원/㎡)": land_price,
                "조회상태": pnu_info["status"]
            })

            progress_bar.progress((i + 1) / total_count)

        status_text.text("✨ 모든 주소 처리 완료!")
        progress_bar.empty()

        df_result = pd.DataFrame(results_data)

        st.markdown("### 📊 분석 및 조회 결과 미리보기")
        st.dataframe(df_result, use_container_width=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_result.to_excel(writer, index=False, sheet_name='PNU및공시지가조회결과')
        excel_data = output.getvalue()

        st.download_button(
            label="📥 결과 엑셀 파일로 다운로드하기",
            data=excel_data,
            file_name="pnu_and_land_price_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
        )
