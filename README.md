PC 견적 추천 시스템 (RAG & Rule-based)
평소 컴퓨터 부품에 관심이 많아 조립 PC 견적을 짜는 일을 자동화해보고 싶어 시작한 프로젝트입니다. 단순히 챗봇에게 물어보는 수준을 넘어, 실제 다나와 데이터를 기반으로 검색하고 물리적인 호환성까지 체크하는 기능을 구현하는 데 집중했습니다.

프로젝트 개요
개발 기간: 2025.10.03 ~ 2025.10.13 (10일)

개발 인원: 1인

주요 기술: Python, GPT-4o-mini, FAISS, Snowflake Embedding, Streamlit

시스템 구조
이 시스템은 사용자가 입력한 예산과 용도에 맞춰 부품을 찾고 검증하는 4단계를 거칩니다.

요구사항 분석: LLM이 예산 내에서 어느 부품에 비중을 둘지 판단합니다.

부품 검색 (RAG): 가공된 1만 건의 CSV 데이터에서 유사도가 높은 부품을 FAISS 인덱스로 빠르게 찾아옵니다.

견적 생성: 찾아온 부품들을 바탕으로 LLM이 5개의 후보 조합을 만듭니다.

호환성 검증: 파이썬 코드가 소켓, 램 규격, 파워 용량을 계산해 문제가 있는 견적을 걸러냅니다.

주요 구현 내용
1. 데이터 검색 로직 (vector_db.py)
단순한 텍스트 검색은 오타나 유사 명칭을 찾지 못해 벡터 검색(RAG)을 도입했습니다. 한국어 제품명 인식률이 좋은 Snowflake 모델을 사용했습니다.



# 검색 속도를 위해 FAISS 인덱싱을 활용했고, 매번 임베딩하는 시간을 아끼려 캐시 기능을 넣었습니다.
```
def search(self, category, query, top_k=20):
    # 쿼리를 벡터로 변환 후 정규화하여 검색 정확도를 높임
    query_emb = self.model.encode([query])
    faiss.normalize_L2(query_emb.astype('float32'))
    
    # 해당 카테고리(CPU, GPU 등) 인덱스에서 가장 유사한 부품 추출
    scores, indices = self.indexes[category_key].search(query_emb, top_k)
    return results
```
2. 소켓 및 규격 검증 (compatibility.py)
LLM이 가장 자주 틀리는 부분이 AM4와 AM5 소켓을 섞거나 DDR4와 DDR5를 혼용하는 것이었습니다. 이를 해결하기 위해 직접 정규표현식으로 제품명을 분석하는 로직을 짰습니다.



# CPU와 메인보드의 소켓이 물리적으로 맞는지 체크하는 핵심 로직입니다.
```
if any(x in cpu_name for x in ['7500','7600','7800']):
    if any(x in mb_name for x in ['B550','A520','X570']):
        result['호환됨'] = False
        result['문제점'].append("소켓 불일치: AM5 규격 CPU는 해당 메인보드에 장착할 수 없습니다.")
```
3. 전력 계산 엔진 (power_calculator.py)
조립 PC에서 파워 용량이 부족하면 시스템이 멈춥니다. 이를 방지하기 위해 각 부품의 TDP(소비전력)를 합산해 파워 용량과 비교합니다.


```
def calculate_total_power(combo):
    total = 0
    # 제품명에 포함된 숫자를 보고 예상 전력을 더합니다.
    if '4090' in name: total += 450
    elif '4080' in name: total += 320
    # 기타 부품들의 기본 소모 전력 60W를 여유분으로 둡니다.
    total += 60
    return total
```
마치며
처음에는 LLM이 모든 걸 다 해줄 줄 알았는데, 실제로 해보니 하드웨어 규격 같은 숫자 데이터는 파이썬 코드로 직접 검증하는 게 훨씬 정확하다는 걸 배웠습니다.

부품 텍스트가 정형화되어 있지 않아 파싱하는 과정이 꽤 까다로웠지만, 정규표현식을 적절히 활용해 예외 상황을 줄여나간 과정이 가장 기억에 남습니다.
