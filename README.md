🖥️ PC 견적 추천 시스템 (RAG & Rule-based)

> 다나와 실데이터 기반 검색 + 물리적 호환성 검증을 결합한 조립 PC 자동 견적 시스템

평소 PC 부품과 조립에 관심이 많아, 단순히 “챗봇에게 물어보는 견적”을 넘어 실제 부품 데이터 검색(RAG)과 하드웨어 규격 검증(Rule-based)까지 포함한 자동화 시스템을 구현했습니다.

LLM의 장점인 추론·조합 능력과, 코드의 강점인 정확한 규칙 검증을 분리 설계한 것이 핵심 포인트입니다.

---

📌 프로젝트 개요

* 프로젝트명: PC 견적 추천 시스템 (RAG & Rule-based)
* 개발 기간: 2025.10.03 ~ 2025.10.13 (10일)
* 개발 인원: 1인
* 주요 기술 스택

  * Python
  * GPT-4o-mini
  * FAISS
  * Snowflake Embedding
  * Streamlit

---

🧠 시스템 설계 개요

본 시스템은 사용자의 예산과 사용 목적을 입력받아, 아래 4단계를 거쳐 최종 견적을 생성합니다.

```
[사용자 입력]
   ↓
1⃣ 요구사항 분석 (LLM)
   ↓
2⃣ 부품 검색 (RAG + FAISS)
   ↓
3⃣ 견적 조합 생성 (LLM)
   ↓
4⃣ 호환성 검증 (Rule-based Python)
   ↓
[검증된 PC 견적 결과]
```

---

🔍 단계별 상세 설명

1⃣ 요구사항 분석

* 사용자의 예산 / 용도(게임, 사무, 작업 등)를 입력으로 받아
* LLM이 CPU·GPU·RAM 등 부품별 예산 비중을 판단

> 예: 게임용 → GPU 비중 ↑ / 사무용 → CPU·RAM 안정성 ↑

---

2⃣ 부품 검색 (RAG)

* 가공된 다나와 부품 CSV 약 10,000건을 벡터화
* 단순 키워드 검색의 한계를 극복하기 위해 벡터 검색(RAG) 도입
* 한국어 제품명 인식률이 높은 Snowflake Embedding 사용
* FAISS 인덱싱으로 빠른 검색 성능 확보

  핵심 구현 (vector_db.py)

```python
def search(self, category, query, top_k=20):
     쿼리를 벡터로 변환 후 정규화하여 검색 정확도를 높임
    query_emb = self.model.encode([query])
    faiss.normalize_L2(query_emb.astype('float32'))

     해당 카테고리(CPU, GPU 등) 인덱스에서 가장 유사한 부품 추출
    scores, indices = self.indexes[category_key].search(query_emb, top_k)
    return results
```

* 매 요청마다 임베딩을 생성하지 않도록 캐시 구조 적용
* 오타·유사 명칭에도 강인한 검색 성능 확보

---

3⃣ 견적 생성

* 검색된 부품 후보들을 기반으로
* LLM이 5개의 견적 조합을 생성
* 이 단계에서는 의도적으로 LLM의 창의성을 활용

---

4⃣ 호환성 검증 (Rule-based)

LLM이 가장 자주 실수하는 영역인 하드웨어 규격은 코드로 직접 검증했습니다.

LLM의 대표적인 오류

* AM4 ↔ AM5 소켓 혼용
* DDR4 ↔ DDR5 메모리 혼용
* 파워 용량 부족

이를 해결하기 위해 정규표현식 + 규칙 기반 로직을 설계했습니다.

---

🔌 소켓 & 규격 검증

핵심 구현 (compatibility.py)

```python
 CPU와 메인보드의 소켓이 물리적으로 맞는지 체크
if any(x in cpu_name for x in ['7500','7600','7800']):
    if any(x in mb_name for x in ['B550','A520','X570']):
        result['호환됨'] = False
        result['문제점'].append(
            "소켓 불일치: AM5 규격 CPU는 해당 메인보드에 장착할 수 없습니다."
        )
```

* 제품명에서 소켓·칩셋 키워드 추출
* 단순 조건문이지만, 실사용 기준에서는 높은 정확도 확보

---

⚡ 전력 계산 엔진

조립 PC에서 파워 용량 부족은 치명적인 문제이기 때문에,
부품별 예상 소비 전력을 합산해 파워 서플라이와 비교합니다.

핵심 구현 (power_calculator.py)

```python
def calculate_total_power(combo):
    total = 0
     제품명에 포함된 숫자를 보고 예상 전력을 더함
    if '4090' in name: total += 450
    elif '4080' in name: total += 320

     기타 부품 기본 소모 전력 (여유분)
    total += 60
    return total
```

* GPU·CPU 중심의 전력 추정
* 기타 부품은 안전 마진 60W 적용
* 실사용 기준에서 안정적인 파워 추천 가능

---

✨ 프로젝트를 통해 배운 점

* LLM은 추론과 조합에 강하지만, 숫자·규격 검증은 코드가 훨씬 정확하다
* AI 시스템에서 중요한 것은 *모든 걸 LLM에 맡기는 것*이 아니라
  LLM과 Rule-based 로직의 역할 분리
* 비정형 텍스트(부품명)를 다루기 위해 정규표현식 설계 능력의 중요성 체감

---

🚀 향후 개선 아이디어

* TDP DB 고도화 (실제 스펙 기반)
* 케이스·쿨러 물리적 크기 호환성 검증
* 사용자 피드백 기반 추천 로직 개선
* 견적 결과 비교 UI 강화

---

> LLM + RAG + Rule-based 검증을 결합한 실전형 AI 서비스 프로젝트로,
> 단순 데모가 아닌 *실사용을 고려한 시스템 설계*를 목표로 했습니다.
