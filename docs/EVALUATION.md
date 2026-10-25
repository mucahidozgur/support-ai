# RAGAS Değerlendirmesi

Support AI'ın kalite hedefleri müşteri brief'inde tanımlıdır ve RAGAS metrikleriyle
ölçülür. "Çalışıyor gibi" değil, ölçülebilir kalite.

## Metrikler

| Metrik | Ne ölçer? | Hedef |
|---|---|---|
| **faithfulness** | Cevap, verilen context'e ne kadar sadık? (uydurma içermiyor mu?) | **≥ 0.85** |
| **context_precision** | Getirilen chunk'lar soruyla ne kadar isabetli? (sıralama kalitesi) | **≥ 0.75** |
| **answer_relevancy** | Cevap, soruyla ne kadar alakalı? | **≥ 0.80** |

Üçü de LLM tabanlıdır (Groq üzerinden `LangchainLLMWrapper`); embedding gerekmez.

## Test Seti Nasıl Üretilir?

Sentetik test seti, dokümandan LLM ile üretilir — cevabı yalnızca dokümanda bulunan
sorular istenir:

```bash
# API ile:
POST /api/ai/evaluate/generate-set
{"document_id": "<uuid>", "num_questions": 5}
→ {"document_id": "...", "questions": [{"question": "...", "ground_truth": "..."}]}
```

LLM çıktısı `{"questions": [...]}` sarmalayıcısı veya ```json ``` blokları içinde
olsa bile dayanıklı şekilde ayrıştırılır; JSON çözülemezse 400, LLM hatasıysa 502
döner.

## Nasıl Çalıştırılır?

`GROQ_API_KEY` dolu olmalıdır.

```bash
cd backend
python -m scripts.run_evaluation --document-id <uuid> [--num-questions 5]
```

Script akışı: dokümanı bul → sentetik set üret → her soru için
`search_hybrid_rerank(limit=3)` ile context topla → LLM ile cevap üret → RAGAS
`evaluate()` ile üç metriği hesapla.

## Örnek Çıktı

```json
Sentetik test seti (5 soru):
[
  {"question": "SSO nasıl kurulur?", "ground_truth": "Admin panelinde ..."},
  ...
]

RAGAS metrikleri:
{
  "faithfulness": 0.91,
  "answer_relevancy": 0.84,
  "context_precision": 0.79
}
```

Hedefler: F ≥ 0.85, CP ≥ 0.75, AR ≥ 0.80. Eşik altı kalırsa hattın hangi adımı
(ingestion? rerank? prompt?) zayıflattığını trace'lerden izleyebilirsiniz.

## API ile

```bash
POST /api/ai/evaluate/run
{"test_set": [{"question": "...", "ground_truth": "..."}]}
→ {"metrics": {"faithfulness": 0.91, "answer_relevancy": 0.84, "context_precision": 0.79},
   "samples": 1}
```

## Not

`ragas 0.4.3`, `langchain-community` 0.4.x ile uyumsuzdur (kaldırılan vertexai
modüllerini import eder); bu yüzden bağımlılık `langchain-community==0.3.31`'e
pin'lenmiştir. Değerlendirme import'u lazy'dir — uygulama başlangıcını etkilemez.
