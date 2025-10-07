# vector_db.py

import pandas as pd
import numpy as np
import faiss
import pickle
import os
from sentence_transformers import SentenceTransformer


class VectorDB:
    def __init__(self, model_name='Snowflake/snowflake-arctic-embed-m', cache_dir='vector_db_cache'):
        self.model = None
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.indexes = {}
        self.metadata = {}
        
        if self._check_cache():
            print("📦 기존 벡터DB 캐시 발견!")
            self._load_from_cache()
        else:
            print("🔨 벡터DB 캐시 없음 → 새로 구축 시작")
            self._build_from_scratch()
    
    
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
                
                index_path = os.path.join(self.cache_dir, filename)
                self.indexes[category] = faiss.read_index(index_path)
                
                pkl_path = os.path.join(self.cache_dir, f"{category}.pkl")
                with open(pkl_path, 'rb') as f:
                    self.metadata[category] = pickle.load(f)
                
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
            if os.path.exists(filename):
                self._process_csv(filename, category)
            else:
                print(f"  ⚠️ 파일 없음: {filename}")
        
        self._save_to_cache()
        print("✅ 벡터DB 구축 및 저장 완료!")
    
    
    def _process_csv(self, csv_path, category):
        print(f"\n[{category}] 처리 중: {csv_path}")
        
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        print(f"  데이터: {len(df)}개")
        
        if '텍스트' in df.columns:
            texts = df['텍스트'].astype(str).tolist()
        elif '임베딩_텍스트' in df.columns:
            texts = df['임베딩_텍스트'].astype(str).tolist()
        else:
            texts = df['제품명'].astype(str).tolist()
        
        print(f"  임베딩 생성 중...")
        embeddings = self.model.encode(texts, show_progress_bar=False)
        embeddings = np.array(embeddings).astype('float32')
        
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)
        faiss.normalize_L2(embeddings)
        index.add(embeddings)
        
        self.indexes[category] = index
        self.metadata[category] = df.to_dict('records')
        
        print(f"  ✅ 완료: {len(df)}개")
    
    
    def _save_to_cache(self):
        os.makedirs(self.cache_dir, exist_ok=True)
        
        for category in self.indexes.keys():
            index_path = os.path.join(self.cache_dir, f"{category}.index")
            faiss.write_index(self.indexes[category], index_path)
            
            pkl_path = os.path.join(self.cache_dir, f"{category}.pkl")
            with open(pkl_path, 'wb') as f:
                pickle.dump(self.metadata[category], f)
        
        print(f"💾 캐시 저장 완료: {self.cache_dir}/")
    
    
    def search(self, category, query, top_k=20):
        category_key = None
        for key in self.indexes.keys():
            if key.lower() == category.lower():
                category_key = key
                break
        
        if not category_key:
            print(f"⚠️ 카테고리 없음: {category}")
            return []
        
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