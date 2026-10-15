import streamlit as st
import requests
import pandas as pd
import io
import re

# 페이지 설정
st.set_page_config(page_title="브이월드 개별공시지가 일괄 조회기", page_icon="🏰", layout="wide")

st.title("🏰 브이월드 개별공시지가 자동 일괄 조회 앱")
st.write("주소 목록을 복사·붙여넣기 하시고 브이월드 API 키와 기준연도를 입력하시면, PNU 자동 추출 및 실시간 공시지가 조회가 이루어집니다. 🍰")

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
    placeholder="울산광역시 울주군 삼남읍 가천리 산23\n경상남도 사천시 용현면 온정리 8-5"
)

# 브이월드 API를 이용해 주소로부터 PNU를 찾고 공시지가를 조회하는 함수
def get_land_price(api_key, year, address):
    geo_url = "https://api.vworld.kr/req/search"
    params = {
        "service": "search",
        "request": "search",
        "version": "2.0",
        "crs": "EPSG:4326",
        "size": 1,
        "page": 1,
        "query": address,
        "type": "address",
        "category": "parcel",
        "format": "json",
        "key": api_key
    }
    
    try:
        response = requests.get(geo_url, params=params, timeout=5)
        try:
            res_data = response.json()
        except Exception:
            return {"pnu": "변환실패", "price": "-", "status": "API 응답 오류"}
        
        if res_data.get("response", {}).get("status") == "OK":
            items = res_data["response"]["result"]["items"]
            if items:
                pnu = items[0].get("id", "")
                
                # 개별공시지가 속성 API 호출
                price_url = "https://api.vworld.kr/ned/data/getIndvdLandPriceAttr"
                price_params = {
                    "key": api_key,
                    "domain": "http://localhost",
                    "format": "json",
                    "stdYear": year,
                    "pnu": pnu
                }
                price_resp = requests.get(price_url, params=price_params, timeout=5)
                
                try:
                    price_json = price_resp.json()
                except Exception:
                    return {"pnu": pnu, "price": "-", "status": "지가 API JSON 오류"}
                
                fields = price_json.get("indvdLandPrices", {}).get("field", [])
                if fields:
                    price = fields[0].get("indvdLandPrice", "정보없음")
                    return {"pnu": pnu, "price": price, "status": "성공"}
                else:
                    return {"pnu": pnu, "price": "지가데이터없음", "status": "성공(데이터 없음)"}
                    
        return {"pnu": "검색실패", "price": "-", "status": "주소 검색 결과 없음"}
    except Exception as e:
        return {"pnu": "에러", "price": "-", "status": f"오류: {str(e)}"}

if st.button("🚀 공시지가 폭풍 조회 시작!", type="primary"):
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
            
            # 산번지 여부 파악
            has_mountain = "산" in line
            
            # API를 통해 PNU 및 공시지가 조회
            api_result = get_land_price(vworld_key, std_year, line)
            
            results_data.append({
                "입력주소": line,
                "기준연도": std_year,
                "산번지여부": "산" if has_mountain else "일반",
                "PNU코드": api_result["pnu"],
                "공시지가(원/㎡)": api_result["price"],
                "조회상태": api_result["status"]
            })

            progress_bar.progress((i + 1) / total_count)

        status_text.text("✨ 모든 주소 조회 완료!")
        progress_bar.empty()

        df_result = pd.DataFrame(results_data)

        st.markdown("### 📊 조회 결과 미리보기")
        st.dataframe(df_result, use_container_width=True)

        # 엑셀 파일 다운로드 버튼 생성
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_result.to_excel(writer, index=False, sheet_name='공시지가조회결과')
        excel_data = output.getvalue()

        st.download_button(
            label="📥 결과 엑셀 파일로 다운로드하기",
            data=excel_data,
            file_name="vworld_land_price_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
        )
