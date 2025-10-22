# streamlit_app.py

import streamlit as st
from vector_db import VectorDB
from main import generate_quote, handle_followup
from config import OPENAI_API_KEY

# 페이지 설정
st.set_page_config(
    page_title="PC 견적 추천 시스템",
    page_icon="💻",
    layout="wide"
)




# ===== 벡터DB 초기화 (최초 1회만) =====
if 'vector_db' not in st.session_state:
    with st.spinner('🔨 벡터DB 초기화 중... (최초 실행 시 5~10분 소요)'):
        st.session_state.vector_db = VectorDB()
    st.success('✅ 벡터DB 준비 완료!', icon="✅")

if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

if 'current_combos_text' not in st.session_state:
    st.session_state.current_combos_text = None

if 'selected_quote_text' not in st.session_state:
    st.session_state.selected_quote_text = None


# ===== 헤더 =====
st.title("💻 PC 견적 추천 시스템")
st.markdown("AI 기반 맞춤형 PC 조립 견적을 추천해드립니다.")
st.markdown("---")


# ===== 입력 폼 (3칸) =====
col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    st.subheader("💰 예산")
    budget = st.number_input(
        "예산을 입력하세요 (원)",
        min_value=300000,
        max_value=10000000,
        value=1000000,
        step=100000,
        help="최소 30만원 ~ 최대 1000만원"
    )
    st.caption(f"**{budget:,}원**")

with col2:
    st.subheader("🎯 목적")
    purpose = st.selectbox(
        "PC 사용 목적을 선택하세요",
        [
            "게이밍",
            "사무용",
            "영상편집",
            "3D 작업",
            "AI/딥러닝",
            "방송/스트리밍",
            "코딩/개발"
        ],
        help="주요 사용 목적을 선택해주세요"
    )

with col3:
    st.subheader("📝 참고사항")
    notes = st.text_area(
        "추가 요구사항을 자유롭게 작성하세요",
        placeholder="예시:\n- 림월드 모드를 많이 넣어도 쾌적하게 돌아가야함\n- 화이트 케이스 원함\n- 조용한 쿨러 필요\n- RGB 라이팅 원함",
        height=100,
        help="게임명, 선호 색상, 특정 부품 요구사항 등을 자유롭게 입력하세요"
    )


# ===== 생성 버튼 (중앙 배치) =====
st.markdown("<br>", unsafe_allow_html=True)
col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])

with col_btn2:
    generate_btn = st.button(
        "🎯 견적 생성하기",
        type="primary",
        use_container_width=True
    )

st.markdown("---")


# ===== 견적 생성 로직 =====
if generate_btn:
    if budget < 300000:
        st.error("⚠️ 예산은 최소 30만원 이상이어야 합니다.", icon="⚠️")
    else:
        with st.spinner('🤖 AI가 최적의 부품 조합을 찾고 있습니다... (1~2분 소요)'):
            try:
                quote_combos = generate_quote(
                    budget=budget,
                    purpose=purpose,
                    notes=notes,
                    vector_db=st.session_state.vector_db
                )
                
                st.session_state.current_combos_text = quote_combos
                st.session_state.selected_quote_text = None
                st.session_state.chat_history = []
                st.success('✅ 견적 생성 완료!', icon="✅") 
                st.rerun()
            
            except Exception as e:
                st.error(f"❌ 오류 발생: {str(e)}", icon="❌")


# ===== 결과 표시 =====
if st.session_state.current_combos_text:
    
    # 탭 구성 변경: '견적서 및 수정'과 '통계' 탭으로 통합 (기존 '수정 요청' 탭 제거)
    tab1, tab2 = st.tabs(["💻 견적서 및 수정", "📊 통계"])
    
    with tab1:
        
        # --- 견적 선택 화면: 아직 선택된 견적이 없을 때 ---
        if st.session_state.selected_quote_text is None:
            
            st.markdown("### 📋 추천 견적 선택")
            st.info("AI가 추천한 1, 2, 3순위 조합을 검토하신 후, 최종 견적을 선택해 주세요. (선택 후 수정 가능)", icon="💡")
            
            # 1, 2, 3순위 조합 텍스트 모두 표시
            st.markdown(st.session_state.current_combos_text)
            
            # 조합 텍스트를 구분자(━━━━━━━━━━━━━━━━━━━━)로 나눠서 리스트로 만듭니다.
            # 1. 조합 구분자
            separator = "━━━━━━━━━━━━━━━━━━━━"
            # 2. 조합을 리스트로 분리
            combos_list = st.session_state.current_combos_text.split(separator)
            # 빈 문자열과 첫 번째 헤더를 제거하고, 실제 조합 텍스트만 남깁니다.
            # 3. 실제 견적 텍스트만 추출 (index 1, 2, 3이 1, 2, 3순위 상세 내용이 되도록 가정)
            parsed_quotes = [separator + combo.strip() for combo in combos_list if "📦 부품 구성:" in combo and "총 가격" in combo][:3]
            
            if len(parsed_quotes) > 0:
                st.markdown("---")
                st.subheader("🚀 최종 견적 선택")
                col_s1, col_s2, col_s3 = st.columns(3)
                
                # 선택 버튼 로직 (선택 시 해당 견적 텍스트를 selected_quote_text에 저장)
                if col_s1.button("🥇 1순위 견적 선택", use_container_width=True, key="select_1"):
                    st.session_state.selected_quote_text = parsed_quotes[0]
                    st.session_state.chat_history.append({'type': 'quote', 'content': parsed_quotes[0]})
                    st.rerun()

                if len(parsed_quotes) > 1 and col_s2.button("🥈 2순위 견적 선택", use_container_width=True, key="select_2"):
                    st.session_state.selected_quote_text = parsed_quotes[1]
                    st.session_state.chat_history.append({'type': 'quote', 'content': parsed_quotes[1]})
                    st.rerun()

                if len(parsed_quotes) > 2 and col_s3.button("🥉 3순위 견적 선택", use_container_width=True, key="select_3"):
                    st.session_state.selected_quote_text = parsed_quotes[2]
                    st.session_state.chat_history.append({'type': 'quote', 'content': parsed_quotes[2]})
                    st.rerun()
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 새로운 견적 처음부터 작성", use_container_width=True, key="reset_all"):
                st.session_state.chat_history = []
                st.session_state.current_combos_text = None
                st.session_state.selected_quote_text = None
                st.rerun()
            
        # --- 수정 모드 화면: 견적이 선택되었을 때 ---
        else:
            st.markdown("### ✅ **선택된 최종 견적**")
            # 선택된 견적만 표시
            st.markdown(st.session_state.selected_quote_text) 
            
            # 다운로드 및 초기화 버튼
            col_d1, col_d2 = st.columns([1, 1])
            
            with col_d1:
                st.download_button(
                    label="📥 견적서 다운로드 (TXT)",
                    data=st.session_state.selected_quote_text,
                    file_name=f"pc_견적서_selected.txt",
                    mime="text/plain",
                    use_container_width=True
                )
            
            with col_d2:
                if st.button("🔄 새로운 견적 작성으로 돌아가기", use_container_width=True):
                    st.session_state.chat_history = []
                    st.session_state.current_combos_text = None
                    st.session_state.selected_quote_text = None
                    st.rerun()
            
            st.markdown("---")
            
            # 채팅/수정 기능 통합
            st.markdown("### 💬 견적 수정하기")
            st.info("채팅으로 부품을 변경할 수 있습니다. (예: 'CPU를 AMD로 바꿔줘')", icon="💡")
            
            # 채팅 히스토리 표시
            for msg in st.session_state.chat_history:
                if msg['type'] == 'quote':
                    with st.chat_message("assistant", avatar="🤖"):
                        st.markdown("✅ **선택/수정된 견적입니다.**")
                
                elif msg['type'] == 'user':
                    with st.chat_message("user", avatar="👤"):
                        st.markdown(msg['content'])
                
                elif msg['type'] == 'followup':
                    with st.chat_message("assistant", avatar="🤖"):
                        st.markdown(msg['content'])
            
            # 사용자 입력 (채팅창)
            user_input = st.chat_input(
                "예: CPU를 AMD로 바꿔줘 / GPU를 더 좋은 걸로 업그레이드해줘",
                key="followup_input"
            )
            
            if user_input:
                # 사용자 메시지 추가
                st.session_state.chat_history.append({
                    'type': 'user',
                    'content': user_input
                })
                
                with st.spinner('🔄 견적 수정 중...'):
                    try:
                        # 선택된 견적을 이전 견적으로 사용
                        new_quote = handle_followup(
                            previous_quote=st.session_state.selected_quote_text,
                            user_request=user_input,
                            vector_db=st.session_state.vector_db
                        )
                        
                        st.session_state.selected_quote_text = new_quote # 수정된 견적 업데이트
                        st.session_state.chat_history.append({
                            'type': 'followup',
                            'content': new_quote
                        })
                        
                        st.rerun()
                    
                    except Exception as e:
                        st.error(f"❌ 오류 발생: {str(e)}", icon="❌")
    
    # 통계 탭 (기존 'tab3'은 이제 'tab2'로 변경)
    with tab2:
        st.markdown("### 📊 시스템 정보")
        
        # 벡터DB 통계
        stats = st.session_state.vector_db.get_stats()
        # ... (이하 기존 통계 출력 로직 유지)
        col_s1, col_s2, col_s3 = st.columns(3)
        
        with col_s1:
            st.metric("CPU 데이터", f"{stats.get('CPU', 0):,}개")
            st.metric("GPU 데이터", f"{stats.get('GPU', 0):,}개")
            st.metric("RAM 데이터", f"{stats.get('RAM', 0):,}개")
        
        with col_s2:
            st.metric("SSD 데이터", f"{stats.get('SSD', 0):,}개")
            st.metric("HDD 데이터", f"{stats.get('HDD', 0):,}개")
            st.metric("메인보드 데이터", f"{stats.get('MAINBORD', 0):,}개")
        
        with col_s3:
            st.metric("케이스 데이터", f"{stats.get('CASE', 0):,}개")
            st.metric("파워 데이터", f"{stats.get('POWER', 0):,}개")
            st.metric("쿨러 데이터", f"{stats.get('COOLER', 0):,}개")
        
        total = sum(stats.values())
        st.success(f"**총 부품 데이터: {total:,}개**", icon="✅")



else:
    # 초기 화면 (견적 없을 때)
    st.markdown("## 👋 환영합니다!")
    st.markdown("""
    ### 📌 사용 방법
    1. **예산**을 입력하세요 (30만원 ~ 1000만원)
    2. **목적**을 선택하세요 (게이밍, 사무용 등)
    3. **참고사항**을 자유롭게 작성하세요
    4. **견적 생성하기** 버튼을 클릭하세요
    
    ### 💡 참고사항 작성 예시
    - "림월드 모드 많이 넣어도 쾌적해야 함"
    - "사이버펑크 2077 최고옵션"
    - "화이트 케이스 + RGB 원함"
    - "조용한 쿨러 필수"
    - "AMD CPU 선호"
    
    ### ⚡ 시스템 특징
    - 🤖 GPT-4 기반 AI 추천
    - 🔍 10,000개 이상 부품 데이터
    - ⚙️ 자동 호환성 체크
    - 💬 실시간 채팅 수정
    - ⚡ 전력 소비 분석
    """)
    
    # 예시 카드
    st.markdown("### 📝 인기 견적 예시")
    
    ex_col1, ex_col2, ex_col3 = st.columns(3)
    
    with ex_col1:
        st.info("""
        **💰 가성비 게이밍 PC**
        - 예산: 100만원
        - 목적: 게이밍
        - 참고: 롤, 오버워치 쾌적
        """)
    
    with ex_col2:
        st.info("""
        **🎮 고성능 게이밍 PC**
        - 예산: 250만원
        - 목적: 게이밍
        - 참고: 사이버펑크 최고옵션
        """)
    
    with ex_col3:
        st.info("""
        **🎨 영상편집 작업용 PC**
        - 예산: 200만원
        - 목적: 영상편집
        - 참고: 4K 편집 쾌적
        """)


# ===== 푸터 =====
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray; padding: 20px;'>
    💻 <b>PC 견적 추천 시스템</b> | Powered by GPT-4o-mini & Snowflake Arctic Embed & FAISS<br>
    Made with ❤️ using Streamlit
</div>
""", unsafe_allow_html=True)