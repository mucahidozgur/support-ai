# Demo Scripti (5 dakika)

Müşteriye teslimat demosu. Hazırlık: stack ayakta (`docker compose up -d postgres api`
+ frontend `npm run dev`), `GROQ_API_KEY` dolu, `LANGFUSE_*` anahtarları dolu
(trace için).

## 1. Login (30 sn)

- `http://localhost:3002` → kullanıcı: `alice`, şifre: `x`
- "Kurumsal oturum açma, JWT ile korunuyor." deyin.

## 2. Doküman Yükle + Index (60 sn)

- Dokümanlar sayfası → "Yeni Doküman"
- Örnek içerik: SSO kurulum rehberi (Markdown başlıklı — hiyerarşik chunking'i
  göstermek için `# Kurulum`, `## SAML`, `### Okta` başlıklarıyla)
- Kaydet → otomatik index'lenir.
- "Metin başlık hiyerarşisine göre parçalanıyor; her chunk kendi başlığını taşıyor."

## 3. Chat: Citation'lı Cevap (90 sn)

- AI Asistan → soru: **"Nasıl SSO kurarım?"**
- Cevap stream edilir; altında kaynaklar listelenir (document + chunk + benzerlik).
- Sonrasında `verification` event'i: tüm cümleler kaynaklı → `verified: true`.
- "Cevabın her cümlesi bir chunk'a bağlı; kaynağı olmayan cümle olsaydı
  işaretlenirdi."

## 4. Chat: Alakasız Soru → "Bilgi Yok" (60 sn)

- Soru: **"Fatura tahsilatı nasıl yapılır?"** (KB'de yok)
- Yanıt: *"Bu bilgi knowledge base'de bulunmuyor. Lütfen ilgili dokümanı kontrol
  edin veya uzmanınıza danışın."* + `insufficient_context: true`
- "Güven eşiğinin altında LLM hiç çağrılmadı — sistem uydurmak yerine bilmediğini
  söyledi."

## 5. Corrective Mode (60 sn)

- Aynı soruyu corrective endpoint'le sorun (veya asistan üzerinden corrective mod):
  **"SSO'da Okta yapılandırması?"**
- `rewrite` event'i: sorgu yeniden yazıldı → yeni arama → taslak cevap →
  `critique` event'i → gerekirse `revision`.
- "Agent kendi cevabını eleştiriyor, gerekirse düzeltiyor."

## 6. Admin Dashboard (30 sn)

- Sol menü → Analytics
- 4 KPI kartı: toplam sorgu, ortalama faithfulness, yetersiz context oranı,
  olumlu geri bildirim + son sorgular tablosu + en çok sorulanlar.
- "Her sorgu, kalite metrikleriyle birlikte loglanıyor."

## 7. Langfuse Trace (30 sn)

- Langfuse Cloud → demo projesi
- Son sorgunun trace'ini aç: `search_hybrid`, `rerank`, `verify_citations`
  span'leri + metadata (query, limit, alpha / candidates_count, top_k /
  verified, unsupported_count) + LLM nesilleri.
- "Kara kutu yok: retrieval'dan doğrulamaya her adım izlenebilir."
