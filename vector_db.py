# vector_db.py (디버깅 & 수정 버전)

import pandas as pd
import numpy as np
import faiss
import pickle
import os
from sentence_transformers import SentenceTransformer
import sys
import logging

# 로깅 중복 방지
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VectorDB:
    _instance = None
    _lock = None
    
    def __new__(cls, model_name='dragonkue/snowflake-arctic-embed-l-v2.0-ko', cache_dir='vector_db_cache'):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._is_building = False  # 빌드 중 플래그
        return cls._instance
    
    def __init__(self, model_name='dragonkue/snowflake-arctic-embed-l-v2.0-ko', cache_dir='vector_db_cache'):
        # 이미 초기화되었으면 즉시 반환
        if self._initialized:
            return
        
        # 빌드 중이면 대기 (이중 초기화 방지)
        if self._is_building:
            print("⏳ 벡터DB 구축이 진행 중입니다. 잠시만 기다려주세요...")
            return
        
        self._is_building = True
        self._initialized = True
        self.model = None
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.indexes = {}
        self.metadata = {}
        self.processed_categories = set()  # 이미 처리된 카테고리 추적
        
        try:
            if self._check_cache():
                print("📦 기존 벡터DB 캐시 발견!")
                self._load_from_cache()
            else:
                print("🔨 벡터DB 캐시 없음 → 새로 구축 시작")
                self._build_from_scratch()
        finally:
            self._is_building = False
    
    
    def _check_cache(self):
        if not os.path.exists(self.cache_dir):
            return False
        
        required = ['CPU.index', 'GPU.index', 'RAM.index']
        for filename in required:
            if not os.path.exists(os.path.join(self.cache_dir, filename)):
                return False
        
        return True
    
    
    def _load_from_cache(self):
        print(f"📂 캐시 로드 중: {self.cache_dir}/")
        
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.index'):
                category = filename.replace('.index', '')
                
                # 이미 처리된 카테고리는 스킵
                if category in self.processed_categories:
                    print(f"  ⏭️  [{category}] 이미 로드됨 (스킵)")
                    continue
                
                index_path = os.path.join(self.cache_dir, filename)
                self.indexes[category] = faiss.read_index(index_path)
                
                pkl_path = os.path.join(self.cache_dir, f"{category}.pkl")
                with open(pkl_path, 'rb') as f:
                    self.metadata[category] = pickle.load(f)
                
                self.processed_categories.add(category)
                print(f"  ✅ [{category}] {len(self.metadata[category])}개")
        
        print("✅ 벡터DB 로드 완료!")
    
    
    def _build_from_scratch(self):
        print("🔨 벡터DB 구축 시작 (5~10분 소요)")
        
        print(f"  임베딩 모델 로드: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        
        csv_files = {
            'CPU': '가공데이터/cpu.csv',
            'GPU': '가공데이터/gpu.csv',
            'RAM': '가공데이터/ram.csv',
            'SSD': '가공데이터/ssd.csv',
            'HDD': '가공데이터/hdd.csv',
            'MAINBORD': '가공데이터/mainbord.csv',
            'CASE': '가공데이터/case.csv',
            'POWER': '가공데이터/power.csv',
            'COOLER': '가공데이터/cooler.csv'
        }
        
        for category, filename in csv_files.items():
            # 이미 처리된 카테고리는 스킵
            if category in self.processed_categories:
                print(f"  ⏭️  [{category}] 이미 처리됨 (스킵)")
                continue
            
            if os.path.exists(filename):
                self._process_csv(filename, category)
                self.processed_categories.add(category)
            else:
                print(f"  ⚠️ 파일 없음: {filename}")
        
        self._save_to_cache()
        print("✅ 벡터DB 구축 및 저장 완료!")
    
    
    def _process_csv(self, csv_path, category):
        """
        CSV 파일을 처리하여 임베딩 생성 및 인덱스 구축
        """
        print(f"\n[{category}] 처리 중: {csv_path}")
        
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            print(f"  데이터: {len(df)}개")
            
            # 텍스트 컬럼 선택
            if '텍스트' in df.columns:
                texts = df['텍스트'].astype(str).tolist()
            elif '임베딩_텍스트' in df.columns:
                texts = df['임베딩_텍스트'].astype(str).tolist()
            else:
                texts = df['제품명'].astype(str).tolist()
            
            print(f"  임베딩 생성 중...")
            embeddings = self.model.encode(texts, show_progress_bar=False)
            embeddings = np.array(embeddings).astype('float32')
            
            # FAISS 인덱스 생성
            dimension = embeddings.shape[1]
            index = faiss.IndexFlatIP(dimension)
            faiss.normalize_L2(embeddings)
            index.add(embeddings)
            
            # 결과 저장
            self.indexes[category] = index
            self.metadata[category] = df.to_dict('records')
            
            print(f"  ✅ 완료: {len(df)}개")
            
        except Exception as e:
            print(f"  ❌ 오류 발생: {str(e)}")
            raise
    
    
    def _save_to_cache(self):
        os.makedirs(self.cache_dir, exist_ok=True)
        
        for category in self.indexes.keys():
            # 이미 저장된 파일은 스킵
            index_path = os.path.join(self.cache_dir, f"{category}.index")
            pkl_path = os.path.join(self.cache_dir, f"{category}.pkl")
            
            if os.path.exists(index_path) and os.path.exists(pkl_path):
                print(f"  ⏭️  [{category}] 캐시 파일이 이미 존재 (스킵)")
                continue
            
            try:
                faiss.write_index(self.indexes[category], index_path)
                
                with open(pkl_path, 'wb') as f:
                    pickle.dump(self.metadata[category], f)
                
                print(f"  💾 [{category}] 캐시 저장 완료")
            except Exception as e:
                print(f"  ❌ [{category}] 캐시 저장 실패: {str(e)}")
        
        print(f"💾 전체 캐시 저장 완료: {self.cache_dir}/")
    
    
    def search(self, category, query, top_k=20):
        category_key = None
        for key in self.indexes.keys():
            if key.lower() == category.lower():
                category_key = key
                break
        
        if not category_key:
            print(f"⚠️ 카테고리 없음: {category}")
            return []
        
        # 모델이 없으면 로드
        if self.model is None:
            print(f"  임베딩 모델 로드: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
        
        query_emb = self.model.encode([query])
        query_emb = np.array(query_emb).astype('float32')
        faiss.normalize_L2(query_emb)
        
        scores, indices = self.indexes[category_key].search(query_emb, top_k)
        
        results = []
        for idx, score in zip(indices[0], scores[0]):
            item = self.metadata[category_key][idx].copy()
            item['유사도'] = float(score)
            results.append(item)
        
        return results
    
    
    def get_categories(self):
        return list(self.indexes.keys())
    
    
    def get_stats(self):
        stats = {}
        for category in self.indexes.keys():
            stats[category] = len(self.metadata[category])
        return stats