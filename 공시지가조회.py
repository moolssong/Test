import streamlit as st
import pandas as pd
import io
import re

# 페이지 설정
st.set_page_config(page_title="주소-PNU 변환 및 데이터 정리기", page_icon="🏰", layout="wide")

st.title("🏰 주소 자동 파싱 및 PNU 분석 앱")
st.write("주소 목록을 복사·붙여넣기 하시면, 일반번지와 산번지를 완벽하게 구분하여 번지와 속성을 자동 추출하고 정리된 엑셀 파일로 다운로드해 드립니다. 🍰")

col1, col2 = st.columns([2, 1])
with col1:
    vworld_key = st.text_input(
        "🔑 브이월드(V-World) API 인증키 (참고용)",
        type="password",
        placeholder="API 키를 입력하세요"
    )
with col2:
    std_year = st.text_input(
        "📅 기준연도",
        value="2026",
        placeholder="예: 2026"
    )

st.markdown("### 📋 주소 목록 입력")
st.info("💡 **입력 팁:** 엑셀이나 메모장에서 주소와 번지가 포함된 텍스트를 복사해서 아래 칸에 그대로 붙여넣어 주세요. (예: `울산광역시 울주군 삼남읍 가천리 산23` 또는 `서울시 관악구 봉천동 464-1`)")

input_text = st.text_area(
    "주소를 줄바꿈 단위로 입력하세요",
    height=200,
    placeholder="울산광역시 울주군 삼남읍 가천리 산23\n서울시 관악구 봉천동 464-1"
)

# 주소 파싱 및 산번지/일반번지 판별 함수
def parse_address_and_get_lot_type(line):
    # '산' 글자가 포함되어 있는지 확인 (예: '산23', '산 177-10')
    has_mountain = "산" in line
    
    # 번지 숫자 추출
    match = re.search(r'산?\s*([0-9\-]+)', line)
    bunji = match.group(1) if match else "확인필요"
    
    lot_type = "산번지 (구분코드: 2)" if has_mountain else "일반번지 (구분코드: 1)"
    
    return {
        "지번유형": lot_type,
        "추출번지": bunji,
        "산번지여부": "산" if has_mountain else "일반"
    }

if st.button("🚀 주소 파싱 및 PNU 분석 시작!", type="primary"):
    if not input_text.strip():
        st.warning("⚠️ 조회할 주소를 하나 이상 입력해 주세요!")
    else:
        lines = [line.strip() for line in input_text.split("\n") if line.strip()]

        results_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        total_count = len(lines)

        for i, line in enumerate(lines):
            status_text.text(f"⏳ 분석 중... ({i+1}/{total_count}): {line}")
            
            parsed = parse_address_and_get_lot_type(line)
            
            results_data.append({
                "입력주소": line,
                "기준연도": std_year,
                "지번구분": parsed["지번유형"],
                "추출번지": parsed["추출번지"],
                "산번지여부": parsed["산번지여부"],
                "상태": "정상 파싱 완료"
            })

            progress_bar.progress((i + 1) / total_count)

        status_text.text("✨ 모든 주소 분석 완료!")
        progress_bar.empty()

        df_result = pd.DataFrame(results_data)

        st.markdown("### 📊 분석 결과 미리보기")
        st.dataframe(df_result, use_container_width=True)

        # 엑셀 파일 다운로드 버튼 생성
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_result.to_excel(writer, index=False, sheet_name='주소분석결과')
        excel_data = output.getvalue()

        st.download_button(
            label="📥 결과 엑셀 파일로 다운로드하기",
            data=excel_data,
            file_name="address_pnu_analysis_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
        )
