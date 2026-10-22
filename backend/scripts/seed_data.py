"""Support AI demo verisi: 15 gerçekçi B2B doküman oluşturup index'ler.

Kullanım (container içinden veya host'tan backend/ dizininde):
    python -m scripts.seed_data          # eksikleri ekle (idempotent)
    python -m scripts.seed_data --force  # demo kullanıcısının hepsini sil, baştan oluştur
"""

import argparse
import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine
from app.core.security import deterministic_user_id
from app.schemas.document import DocumentCreate
from app.services.document import DocumentService
from app.services.ingestion import DocumentIngestionService

DEMO_USERNAME = "demo"

SEED_DOCUMENTS: list[dict[str, str]] = [
    {
        "title": "Hizmet Sözleşmesi",
        "content": """SÖZLEŞME: HİZMET SÖZLEŞMESİ
Taraflar: ABC Yazılım A.Ş. (bundan böyle "Sağlayıcı") ve XYZ Müşteri Ltd. Şti. (bundan böyle "Müşteri").

Madde 1: Konu
İşbu sözleşme, Sağlayıcı'nın Müşteri'ye kurumsal web uygulaması geliştirme ve bakım hizmeti sunmasını kapsar. Proje kapsamı, ekte yer alan gereksinim dokümanında tanımlanmıştır.

Madde 2: Süre
Sözleşme imza tarihinden itibaren 12 ay süreyle geçerlidir. Taraflardan biri, sürenin bitiminden en az 30 gün önce yazılı bildirimde bulunmadığı takdirde sözleşme aynı koşullarla bir yıl daha uzar.

Madde 3: Teslimat ve Kabul
Sağlayıcı, her iki haftada bir çalışır durumda yazılım sürümü teslim eder. Müşteri, teslimattan sonra 10 iş günü içinde kabul testlerini tamamlar. Bu süre içinde bildirilmeyen aykırılıklar için yazılım kabul edilmiş sayılır.

Madde 4: Hizmet Seviyeleri
Uygulamanın aylık erişilebilirlik oranı %99,5'in altına düşemez. Kritik hatalara 4 saat içinde müdahale edilir; kritik olmayan hatalar 3 iş günü içinde giderilir.

Madde 5: Ödeme Koşulları
Toplam proje bedeli 840.000 TL'dir. Ödemeler aylık eşit taksitler halinde, her ayın ilk iş günü faturalandırılır. Fatura tarihinden itibaren 30 gün içinde ödenmeyen tutarlar için aylık %2 gecikme faizi uygulanır. Ek iş talepleri, 2.500 TL saatlik birim fiyat üzerinden ücretlendirilir.

Madde 6: Fikri Mülkiyet
Proje kapsamında üretilen tüm kaynak kodun telif hakları, ödemelerin tamamlanmasının ardından Müşteri'ye devredilir. Sağlayıcı, açık kaynak bileşenlerin kendi lisans koşullarının korunduğunu beyan eder.

Madde 7: Gizlilik
Taraflar, sözleşme kapsamında edindikleri ticari sırları üçüncü kişilerle paylaşmaz. Bu yükümlülük sözleşmenin sona ermesinden sonra 5 yıl süreyle devam eder.

Madde 8: Fesih
Taraflardan biri sözleşme yükümlülüklerini ağır biçimde ihlal ederse, diğer taraf 15 günlük ihtarlı süre sonunda sözleşmeyi feshedebilir. Haksız fesihte, fesheden taraf kalan dönem bedelinin %20'sini tazminat olarak öder.""",
    },
    {
        "title": "Gizlilik Sözleşmesi",
        "content": """GİZLİLİK SÖZLEŞMESİ (NDA)

Taraflar: ABC Yazılım A.Ş. ve XYZ Müşteri Ltd. Şti.

1. Amaç
Bu sözleşme, taraflar arasında yürütülecek ticari görüşmeler sırasında paylaşılacak gizli bilgilerin korunmasını amaçlar.

2. Gizli Bilgi Tanımı
Gizli bilgi; teknik, ticari, finansal ve stratejik her türlü bilgiyi kapsar. Buna kaynak kod, algoritmalar, müşteri listeleri, fiyatlandırma politikaları, iş planları ve sözleşme taslakları dahildir. Sözlü paylaşılan bilgiler, paylaşımı izleyen 15 gün içinde yazılı hale getirildiğinde gizli sayılır.

3. Yükümlülükler
Alıcı taraf, gizli bilgiyi yalnızca görüşmenin amacı doğrultusunda kullanır. Bilgiyi, bilmesi gereken çalışanları dışında kimseyle paylaşmaz. Bu çalışanların da yazılı gizlilik taahhüdü vermesi zorunludur.

4. İstisnalar
Kamuya mal olmuş bilgiler, alıcının bağımsız olarak geliştirdiği bilgiler, üçüncü bir kişiden yasal yollarla edinilen bilgiler ve mahkeme kararıyla açıklanması zorunlu tutulan bilgiler bu sözleşmenin kapsamı dışındadır.

5. Süre
Gizlilik yükümlülüğü, bu sözleşmenin imzalanmasından itibaren 5 yıl süreyle geçerlidir. Ticari sır niteliğindeki bilgiler için süre sınırı uygulanmaz.

6. İhlal
İhlal durumunda, ihlalin kapsamına göre 250.000 TL'ye kadar cezai şart uygulanır. Cezai şartın ödenmesi, uğranan zararın tazmini hakkını ortadan kaldırmaz.

7. Uyuşmazlık Çözümü
Bu sözleşmeden doğan uyuşmazlıklarda İstanbul mahkemeleri ve icra daireleri yetkilidir.""",
    },
    {
        "title": "Tedarikçi Sözleşmesi",
        "content": """TEDARİKÇİ SÖZLEŞMESİ

Taraflar: ABC Yazılım A.Ş. ve BulutAltyapı Hizmetleri A.Ş.

1. Konu
BulutAltyapı, ABC Yazılım'a üretim ortamı için sanal sunucu, depolama ve ağ hizmetleri sağlayacaktır.

2. Hizmet Kapsamı
- 8 sanal sunucu (16 vCPU, 64 GB RAM)
- 2 TB NVMe depolama
- Günlük otomatik yedekleme (30 gün saklama)
- 7/24 teknik destek

3. Hizmet Seviyesi Anlaşması (SLA)
Aylık erişilebilirlik taahhüdü %99,9'dur. Taahhüdün altında kalınan her saat için, ilgili aylık ücretin %5'i oranında hizmet kredisi uygulanır.

4. Ödeme Koşulları
Aylık hizmet bedeli 45.000 TL'dir. Faturalar ayın 1'inde kesilir, 30 gün vadeli ödenir. Geciken ödemelerde aylık %3 gecikme faizi uygulanır. Üç aylık ödemeyi geciktiren ABC Yazılım'ın hizmeti durdurulabilir.

5. Süre ve Yenileme
Sözleşme 24 ay süreyle geçerlidir. Taraflar dönem bitiminden 60 gün önce fesih bildirmezse, sözleşme 12 aylık dönemlerle otomatik yenilenir.

6. Veri Güvenliği
BulutAltyapı, verileri Türkiye sınırları içinde saklar. Kişisel verilerin işlenmesinde KVKK'ya uyum esastır. ABC Yazılım, sözleşme bitiminde verilerinin 30 gün içinde dışa aktarılmasını talep edebilir.

7. Fesih
Her iki taraf, 90 gün önceden yazılı bildirimle sözleşmeyi feshedebilir. SLA taahhüdünün art arda 3 ay tutturulamaması, ABC Yazılım'a tazminatsız fesih hakkı verir.""",
    },
    {
        "title": "Freelance Sözleşmesi",
        "content": """FREELANCE DANIŞMANLIK SÖZLEŞMESİ

Taraflar: ABC Yazılım A.Ş. ve Serbest Danışman Deniz Yılmaz.

1. Hizmetin Tanımı
Danışman, ABC Yazılım'ın yeni ürün arayüzü için UX araştırması yürütecek; kullanıcı görüşmeleri, akış diyagramları ve tıklanabilir prototipler teslim edecektir.

2. Süre ve Çalışma Şekli
Çalışma 3 aylık dönemi kapsar. Danışman haftada 20 saat hizmet verir; çalışma saatlerini kendisi planlar, haftalık ilerleme raporu sunar.

3. Teslimatlar
- 1. ay sonu: Kullanıcı araştırma raporu (en az 10 görüşme)
- 2. ay sonu: Bilgi mimarisi ve akış diyagramları
- 3. ay sonu: Tıklanabilir prototip ve tasarım sistemi önerisi

4. Ücret ve Ödeme
Toplam bedel 180.000 TL'dir. Ödeme, her teslimatın kabulünde üç eşit taksit halinde yapılır. Ödemeler serbest meslek makbuzu karşılığında, 15 gün içinde banka havalesiyle gerçekleştirilir.

5. Telif
Teslim edilen tüm tasarım dosyalarının mali hakları, bedelin tamamı ödendiğinde ABC Yazılım'a geçer. Danışman, portföyünde göstermek için 6 ay sonra izin isteyebilir.

6. Gizlilik
Danışman, proje kapsamında öğrendiği tüm bilgileri gizli tutar. İhlal halinde sözleşme bedelinin %25'i oranında cezai şart uygulanır.

7. Fesih
Taraflar 15 gün önceden yazılı bildirimle sözleşmeyi feshedebilir. Fesih anına kadar tamamlanan ve kabul edilen işlerin bedeli ödenir.""",
    },
    {
        "title": "Proje Brief",
        "content": """PROJE BRİEF: CRM ENTEGRASYONU

1. Özet
Mevcut satış süreçlerinin tek bir platformda toplanması için Salesforce benzeri bir CRM çözümünün mevcut ERP sistemine entegre edilmesi planlanmaktadır. Proje, satış ekibinin verimliliğini artırmayı ve müşteri verilerini merkezileştirmeyi hedefler.

2. Arka Plan
Satış ekibi şu anda fırsatları e-tablolarda takip ediyor; bu durum veri kaybına ve raporlama hatalarına yol açıyor. Yönetim, çeyreklik hedeflerin tutturulamamasının ana nedeninin dağınık veri olduğunu tespit etti.

3. Hedefler
- Satış döngüsünü %20 kısaltmak
- Fırsat takibini tek araçta toplamak
- Haftalık raporlamayı otomatikleştirmek
- Müşteri verilerinin ERP ile çift yönlü senkronizasyonunu sağlamak

4. Kapsam Dışı
Pazarlama otomasyonu, müşteri destek modülü ve mobil uygulama bu projenin kapsamı dışındadır.

5. Kısıtlar
Proje bütçesi 1.200.000 TL'yi aşamaz. Canlıya geçiş, yıl sonu yoğunluğundan önce, en geç Kasım ayında tamamlanmalıdır.

6. Başarı Kriterleri
- Satış ekibinin %90'ının sistemi günlük kullanması
- Veri doğruluk oranının %95'in üzerine çıkması
- Entegrasyonun kesintisiz 30 gün çalışması

7. Paydaşlar
Proje sponsoru: Satış Direktörü. Ürün sahibi: CRM Uzmanı. Teknik ekip: 2 backend, 1 frontend geliştirici. Onay mercileri: CIO ve CFO.""",
    },
    {
        "title": "Proje Planı",
        "content": """PROJE PLANI: CRM ENTEGRASYONU

1. Genel Bakış
Proje 6 fazdan oluşur; toplam süre 24 hafta, toplam bütçe 1.200.000 TL'dir. Kritik yol üzerindeki aktiviteler Faz 2 ve Faz 4'tür.

2. Fazlar ve Zaman Çizelgesi
Faz 1 - Keşif ve Analiz (1-3. hafta): Mevcut süreçlerin dokümante edilmesi, veri modelinin çıkarılması, entegrasyon noktalarının belirlenmesi.
Faz 2 - Mimari Tasarım (4-6. hafta): API sözleşmelerinin yazılması, güvenlik modelinin tasarlanması, ortamların hazırlanması.
Faz 3 - Geliştirme (7-16. hafta): İki haftalık sprint'ler halinde CRM modüllerinin geliştirilmesi.
Faz 4 - Veri Migrasyonu (14-18. hafta): Mevcut e-tablolardaki verilerin temizlenmesi, eşlenmesi ve taşınması.
Faz 5 - Test ve Pilot (19-21. hafta): Kabul testleri, pilot ekiple canlı deneme.
Faz 6 - Canlıya Geçiş (22-24. hafta): Eğitimler, geçiş ve 2 hafta hiper bakım.

3. Kaynaklar
2 backend geliştirici, 1 frontend geliştirici, 1 CRM uzmanı, yarı zamanlı 1 proje yöneticisi.

4. Milestone'lar
- Hafta 6: Mimari onayı (CIO)
- Hafta 10: İlk çalışan sürüm (demo)
- Hafta 16: Geliştirme tamamlanması
- Hafta 21: Pilot kabulü
- Hafta 24: Canlıya geçiş

5. Riskler
Veri migrasyonundaki gecikme kritik yolu etkiler; bu yüzden Faz 4, Faz 3 ile paralel yürütülür. Bütçe aşımına karşı %10 rezerv ayrılmıştır.

6. İletişim
Haftalık durum toplantısı her Pazartesi 10:00'da yapılır. İlerleme raporu her Cuma paydaşlara gönderilir.""",
    },
    {
        "title": "Risk Analizi",
        "content": """RİSK ANALİZİ: CRM ENTEGRASYONU

1. Yöntem
Riskler olasılık (1-5) ve etki (1-5) olmak üzere iki boyutta değerlendirildi. Skor 12'nin üzerinde olan riskler "yüksek" olarak sınıflandırıldı ve azaltma planı hazırlandı.

2. Yüksek Riskler

R1 - Veri kaybı (Olasılık 3, Etki 5, Skor 15): Migrasyon sırasında müşteri kayıtlarının kaybolması. Azaltma: Migrasyon öncesi tam yedekleme, kuru koşu üç kez tekrarlanacak, satır bazında doğrulama raporu üretilecek.

R2 - Entegrasyon kesintisi (Olasılık 4, Etki 4, Skor 16): ERP bağlantısının canlıda kopması. Azaltma: Devre kesici (circuit breaker) deseni, kuyruk tabanlı yeniden deneme, gece 02:00-04:00 arası bakım penceresi.

R3 - Kullanıcı direnci (Olasılık 4, Etki 3, Skor 12): Satış ekibinin sistemi benimsememesi. Azaltma: Erken pilot, şampiyon kullanıcılar, haftalık eğitim ofis saatleri, üst yönetim desteği.

3. Orta Riskler

R4 - Bütçe aşımı (2x4=8): Kapsam kayması nedeniyle ek maliyet. Azaltma: Değişiklik talep süreci, %10 rezerv, haftalık bütçe izleme.
R5 - Tedarikçi gecikmesi (2x4=8): CRM lisans temininde gecikme. Azaltma: Lisansın erken satın alınması, alternatif tedarikçi listesi.
R6 - Güvenlik açığı (2x4=8): API sızıntısı. Azaltma: Penetrasyon testi, OAuth2 zorunluluğu, log izleme.

4. İzleme
Riskler iki haftada bir gözden geçirilir. Skoru 12'nin üzerine çıkan her risk, yönlendirme komitesine raporlanır. Proje sonunda tüm risklerin kapatıldığı doğrulanır.""",
    },
    {
        "title": "Haftalık Sprint Toplantısı",
        "content": """TOPLANTI NOTU: HAFTALIK SPRINT TOPLANTISI
Tarih: Pazartesi 10:00 | Katılımcılar: Ürün sahibi, 3 geliştirici, proje yöneticisi

1. Geçen Haftanın Gözden Geçirilmesi
- Sprint hedefi olan "müşteri listesi ekranı" %80 tamamlandı.
- Arama filtresi beklenenden yavaş çalışıyor; indeksleme eksik.
- İki hata (hata #412 ve #417) düzeltildi, test ortamına alındı.

2. Blokajlar
- Tasarım ekibinden ikon seti hâlâ bekleniyor (3 gündür gecikmeli).
- Test ortamı veritabanı dün 2 saat erişilemezdi; altyapı ekibi bilgilendirildi.

3. Bu Haftanın Hedefleri
- Müşteri listesi ekranının tamamlanması
- Dışa aktarma (CSV) özelliğinin geliştirilmesi
- Performans iyileştirmesi: liste sorgusuna indeks eklenmesi

4. Aksiyon Maddeleri
- [ ] Ali: Arama sorgusuna veritabanı indeksi ekle (Çarşamba)
- [ ] Zeynep: CSV dışa aktarma servisini yaz (Perşembe)
- [ ] Mert: İkon seti için tasarım ekibiyle toplantı ayarla (bugün)
- [ ] Proje Yöneticisi: Test ortamı kesintisi için kök neden raporu talep et (Cuma)
- [ ] Herkes: Kod inceleme sürecini yarın 14:00'da toplu yap

5. Kararlar
- Sprint süresi iki haftada kalacak; retrospektif Cuma 16:30'a alındı.
- Yeni özellikler için önce teknik tasarım dokümanı zorunlu oldu.

6. Sonraki Toplantı
Gelecek Pazartesi 10:00, sprint gözden geçirme ile başlayacak.""",
    },
    {
        "title": "Müşteri Görüşmesi Notları",
        "content": """TOPLANTI NOTU: MÜŞTERİ GÖRÜŞMESİ
Tarih: Perşembe 14:00 | Katılımcılar: XYZ Müşteri tarafında satın alma müdürü ve IT müdürü; bizden ürün sahibi ve çözüm mimarı

1. Gündem
Yeni portal modülünün gereksinimlerinin netleştirilmesi.

2. Görüşülen Konular

Portal Modülü:
- Kullanıcılar kendi profillerini güncelleyebilmeli.
- Fatura geçmişi son 24 ay görüntülenebilmeli.
- Destek talebi oluşturma ve takip etme olmalı.
- Talep durum değişiminde e-posta bildirimi zorunlu.

Güvenlik:
- İki faktörlü doğrulama (2FA) ilk sürümde olmasa da yol haritasında yer almalı.
- Şifre politikası: en az 12 karakter, büyük/küçük harf ve rakam zorunluluğu.
- Oturum süresi 30 dakika boşta kalınca sonlanmalı.

Entegrasyon:
- ERP'deki fatura verisi portal ile günlük senkronize olmalı (gece 03:00).
- Senkronizasyon hataları otomatik e-postayla IT ekibine bildirilmeli.

3. Açık Sorular
- Portal kaç kullanıcıya hizmet verecek? (Müşteri tahmini: 5.000 - 10.000)
- Mevcut logo ve marka kılavuzu ne zaman teslim edilecek? (Söz: 2 hafta)
- Test kullanıcı havuzunu kim yönetecek? (IT müdürü)

4. Aksiyon Maddeleri
- [ ] Ürün sahibi: Gereksinimleri backlog'a işle (Pazartesi)
- [ ] Çözüm mimarı: 2FA için teknik fizibilite notu hazırla (1 hafta)
- [ ] Müşteri IT müdürü: Test kullanıcı listesini gönder (Cuma)
- [ ] Proje yöneticisi: Bir sonraki görüşmeyi 2 hafta sonraya planla

5. Kararlar
- Portal ilk sürümü 3 ayda yayınlanacak; 2FA ikinci sürüme ertelendi.
- Haftalık senkronizasyon toplantısı Salı 11:00'a sabitlendi.""",
    },
    {
        "title": "Yönetim Toplantısı",
        "content": """TOPLANTI NOTU: AYLIK YÖNETİM TOPLANTISI
Tarih: Ayın ilk Çarşambası 09:30 | Katılımcılar: CEO, CTO, CFO, Satış Direktörü, İK Müdürü

1. Finansal Durum
- Çeyreklik gelir hedefin %8 altında; ana neden iki büyük teklifin ertelenmesi.
- Operasyonel giderler bütçeyle uyumlu.
- Nakit akışı sağlıklı; 6 aylık rezerv mevcut.

2. Ürün ve Teknoloji
- CRM entegrasyon projesi plana uygun ilerliyor (Faz 3, %60).
- AI Asistan özelliği beta kullanıcılarıyla test ediliyor; ilk geri bildirimler olumlu.
- Teknik borç listesi 120 maddeden 85'e indirildi.

3. Satış ve Pazarlama
- İkinci çeyrek hedefi: 15 yeni kurumsal müşteri.
- Pazarlama bütçesinin %30'u içerik pazarlamasına kaydırılacak.
- Fiyatlandırma revizyonu için danışman görüşü alınacak.

4. İnsan Kaynakları
- 3 yeni pozisyon onaylandı: 2 kıdemli geliştirici, 1 satış temsilcisi.
- Hibrit çalışma modeli devam edecek; ofis günleri Salı ve Perşembe.
- Eğitim bütçesi kişi başı yıllık 30.000 TL'ye çıkarıldı.

5. Aksiyon Maddeleri
- [ ] CFO: Geciken teklifler için takip planı sun (1 hafta)
- [ ] Satış Direktörü: Fiyatlandırma danışmanı için teklif topla (2 hafta)
- [ ] CTO: AI Asistan beta sonuçlarını yönetime raporla (ay sonu)
- [ ] İK: Yeni pozisyonlar için ilanları yayınla (bu hafta)

6. Kararlar
- Yılın ikinci yarısında yeni ofis yatırımı yapılmayacak.
- AI yatırımları bütçeden öncelikli fonlanacak.""",
    },
    {
        "title": "API Dokümantasyonu",
        "content": """API DOKÜMANTASYONU

1. Genel Bilgiler
Temel URL: https://api.support.local/v1
Kimlik doğrulama: Tüm isteklerde Authorization: Bearer <token> başlığı zorunludur. Token, /auth/login uç noktasından alınır ve 24 saat geçerlidir.

2. Uç Noktalar

GET /documents
Doküman listesini döndürür. Sayfalama için limit (varsayılan 20, en fazla 100) ve offset parametreleri kullanılır. Yanıt: { "items": [...], "total": 154, "limit": 20, "offset": 0 }.

POST /documents
Yeni doküman oluşturur. Gövde: { "title": "string", "content": "string" }. Yanıt 201, oluşturulan doküman nesnesi. Başlık 1-255 karakter, içerik en az 1 karakter olmalıdır.

GET /documents/{id}
Tek dokümanı döndürür. Doküman yoksa 404 döner.

PUT /documents/{id}
Dokümanı günceller. Gövde: { "title"?: "string", "content"?: "string" }. Yalnızca gönderilen alanlar güncellenir.

DELETE /documents/{id}
Dokümanı ve ilişkili tüm chunk'ları siler. Başarıda 204 döner.

POST /documents/{id}/index
Dokümanı chunk'layıp embedding'lerini index'ler. Yanıt: { "chunks_created": 12, "chunks_deleted": 0 }.

POST /ai/chat
Dokümanlar üzerinde soru-cevap. Gövde: { "query": "string", "document_ids"?: ["uuid"], "top_k"?: 5 }. Yanıt, SSE akışıdır: sources, token ve done event'leri.

POST /ai/agent
Çok adımlı ajan: özet, aksiyon maddeleri ve karşılaştırma. Gövde: { "query": "string", "document_ids"?: ["uuid"], "top_k"?: 5 }. SSE event'leri: intent, sources, token, done.

3. Hata Kodları
400: Geçersiz gövde. 401: Token eksik veya süresi dolmuş. 404: Kaynak bulunamadı. 422: Doğrulama hatası. 500: Sunucu hatası.

4. Hız Sınırları
Dakikada 60 istek; aşımında 429 döner. Retry-After başlığı ile bekleme süresi bildirilir.""",
    },
    {
        "title": "Mimari Karar Kaydı",
        "content": """MİMARİ KARAR KAYDI (ADR): VEKTÖR ARAMA İÇİN POSTGRESQL + PGVECTOR

Durum: Kabul edildi
Tarih: 15 Mart
Karar veren: Çözüm mimarı, CTO

1. Bağlam
Doküman Q&A özelliği, anlamsal benzerlik araması (semantic search) gerektiriyor. İki seçenek değerlendirildi: (a) özel vektör veritabanı (Pinecone, Weaviate), (b) mevcut PostgreSQL üzerinde pgvector eklentisi.

2. Karar
pgvector kullanılacak. Embedding boyutu 384 (BAAI/bge-small-en-v1.5 modeli). Benzerlik metriği kosinüs. Eşik değeri 0.55.

3. Gerekçeler
- Tek veritabanı: Dokümanlar zaten PostgreSQL'de; ayrı sistem operasyonel yük getirir.
- Maliyet: Ekstra servis yok; pgvector açık kaynak ve mevcut altyapıda çalışır.
- Yeterli ölçek: Beklenen hacim 1 milyon chunk'ın altında; pgvector bu ölçekte rahat performans verir.
- Tutarlılık: Doküman ve embedding aynı transaction'da yönetilebilir.

4. Sonuçları
- Olumlu: Altyapı basitliği, tek yedekleme noktası, JOIN ile metadata filtreleme.
- Olumsuz: Çok büyük ölçeklerde (>10M vektör) performans düşebilir; o durumda ayrı vektör veritabanına geçiş yeniden değerlendirilir.

5. Alternatifler
Pinecone: Yönetilen hizmet, hızlı kurulum, ancak ek maliyet ve veri gizliliği riski. Weaviate: Güçlü filtreleme, ancak ayrı operasyon yükü. Her ikisi de mevcut ekip büyüklüğü için gereksiz bulundu.

6. Geçiş Planı
Eğer 10 milyon chunk eşiği aşılırsa, pgvector'deki veriler embedding'leri yeniden üretmeden Pinecone'a taşınabilir; bunun için embedding'ler ham vektör olarak saklanmaya devam edecek.""",
    },
    {
        "title": "Deployment Rehberi",
        "content": """DEPLOYMENT REHBERİ

1. Ön Gereksinimler
- Docker 24+ ve Docker Compose v2
- En az 8 GB RAM (embedding modeli bellekte tutulur)
- .env dosyası (GROQ_API_KEY, DATABASE_URL ve diğer ayarlar)

2. Yerel Kurulum

Adım 1: Depoyu klonlayın ve kök dizine geçin.
Adım 2: .env.example dosyasını .env olarak kopyalayın; GROQ_API_KEY değerini kendi anahtarınızla doldurun.
Adım 3: docker compose up -d komutunu çalıştırın. İlk çalıştırmada postgres container'ı pgvector eklentisini ve support_test veritabanını init script'i ile oluşturur.
Adım 4: API'nin hazır olduğunu doğrulayın: curl http://localhost:8002/health yanıtı {"status":"ok"} olmalıdır.
Adım 5: Veritabanı şeması için migration çalıştırın: docker compose exec api alembic upgrade head.
Adım 6: Demo verisi için: docker compose exec api python -m scripts.seed_data.

3. Güncelleme Akışı
- Kod değişikliği: api container'ı --reload ile çalıştığı için bind mount üzerinden otomatik yansır.
- .env değişikliği: docker compose up -d api ile container yeniden oluşturulmalıdır; restart env değerlerini yeniden okumaz.
- Şema değişikliği: Yeni migration yazın, sonra docker compose exec api alembic upgrade head.

4. Rollback
Son sürümde sorun çıkarsa: git revert ile değişikliği geri alın, docker compose up -d --force-recreate api çalıştırın. Veritabanı rollback için alembic downgrade -1 kullanın.

5. Yedekleme
Postgres verisi docker compose exec postgres pg_dump -U support support > backup.sql ile günlük yedeklenir. Yedekler en az 30 gün saklanır.

6. Sorun Giderme
- API 500 dönüyorsa: docker compose logs api ile logları inceleyin.
- Embedding hatası varsa: hf_cache volume'ünün bağlı olduğunu doğrulayın.
- Veritabanı bağlantı hatası: docker compose ps ile postgres'in healthy olduğunu kontrol edin.""",
    },
    {
        "title": "Aylık Performans Raporu",
        "content": """AYLIK PERFORMANS RAPORU

Dönem: Haziran
Hazırlayan: Operasyon Müdürü

1. Yönetici Özeti
Bu ay gelir 2.4 milyon TL olarak gerçekleşti; hedefin %4 üzerinde. Yeni müşteri sayısı 6, churn oranı %1.2. AI Asistan özelliğinin lansmanı planlandığı gibi ay sonunda yapıldı.

2. Gelir Dağılımı
- Abonelik gelirleri: 1.9 milyon TL (%79)
- Profesyonel hizmetler: 320 bin TL (%13)
- Eğitim ve danışmanlık: 180 bin TL (%8)

3. Kullanım Metrikleri
- Aktif kullanıcı: 3.400 (önceki ay: 3.100)
- Ortalama oturum süresi: 18 dakika (önceki ay: 15)
- Doküman başına ortalama sorgu: 4.2
- En çok kullanılan özellik: Doküman arama (%62)

4. Hizmet Seviyeleri
- Uptime: %99.91 (hedef %99.5) — hedef tuttu
- Ortalama yanıt süresi: 210 ms (hedef 300 ms) — hedef tuttu
- Açık kritik hata: 0

5. Müşteri Başarısı
- NPS: 54 (önceki ay: 49)
- Destek talebi: 210, ortalama çözüm süresi 6 saat
- En sık talep konusu: Entegrasyon yardımı (%35)

6. Önümüzdeki Ay Hedefleri
- Aktif kullanıcıyı 3.800'e çıkarmak
- Churn'ü %1'in altında tutmak
- AI Asistan kullanımını toplam sorguların %25'ine taşımak
- İki yeni entegrasyonu (Slack, Google Drive) yayınlamak

7. Aksiyonlar
- [ ] Pazarlama: Slack entegrasyonu için lansman planı hazırla
- [ ] Ürün: NPS yorumlarındaki ilk 5 isteği backlog'a al
- [ ] Operasyon: Destek süresini 5 saate indirmek için bilgi tabanını genişlet""",
    },
    {
        "title": "Müşteri Memnuniyet Raporu",
        "content": """MÜŞTERİ MEMNUNİYET RAPORU

Dönem: İkinci Çeyrek
Hazırlayan: Müşteri Başarısı Ekibi

1. Özet
Çeyreklik NPS 54 olarak ölçüldü; hedef 50 idi, hedef aşıldı. Anket 420 müşterinin 312'sinden yanıt alındı (yanıt oranı %74). Genel memnuniyet puanı 4.3/5.

2. NPS Dağılımı
- Destekleyenler (9-10): %62
- Pasifler (7-8): %30
- Kötüleyenler (0-6): %8

3. Temalar ve Bulgular

Güçlü Yönler:
- Doküman arama hızı: "Sonuçlar saniyeler içinde geliyor." (sık tekrar eden yorum)
- Arayüz sadeliği: Yeni kullanıcıların eğitim almadan sistemi kullanabildiği belirtildi.
- Destek ekibi: Ortalama memnuniyet 4.6/5.

Gelişim Alanları:
- Mobil deneyim: Kullanıcıların %28'i mobil görünümü yetersiz buluyor.
- Bildirim ayarları: Daha ince ayarlı bildirim tercihleri isteniyor (%22).
- Offline erişim: Saha ekipleri çevrimdışı erişim talep ediyor (%15).
- AI Asistan: Beta kullanıcılarının %40'ı daha derin özetleme istiyor.

4. Segment Analizi
Kurumsal müşterilerde NPS 61, KOBİ segmentinde 47. KOBİ'lerdeki ana şikayet fiyatlandırma esnekliği; yıllık ödeme seçeneği bu segmentte talep görüyor.

5. Kayıp Analizi
Çeyrekte 4 müşteri kaybedildi; 3'ü bütçe kısıtı, 1'i rakip ürüne geçiş nedeniyle. Rakibe geçen müşteri, daha gelişmiş raporlama aradığını belirtti.

6. Aksiyon Planı
- [ ] Mobil görünüm iyileştirmesi önceliklendirildi (3. çeyrek sprint planına alındı)
- [ ] KOBİ için yıllık ödeme kampanyası hazırlanacak
- [ ] Raporlama modülü yol haritasına eklendi
- [ ] NPS kötüleyenlerine birebir görüşme planlandı (ilk 10 hesap)""",
    },
]


async def seed(force: bool) -> None:
    """Demo dokümanlarını oluşturur ve index'ler (idempotent)."""
    owner_id = UUID(deterministic_user_id(DEMO_USERNAME))
    async with AsyncSession(engine) as db:
        documents = DocumentService(db, owner_id)
        ingestion = DocumentIngestionService(db, owner_id)

        existing_docs, _ = await documents.list(limit=100, offset=0)
        existing_titles = {doc.title for doc in existing_docs}
        if force:
            for doc in existing_docs:
                await documents.delete(doc.id)
            existing_titles = set()

        created = 0
        skipped = 0
        chunks_total = 0
        for item in SEED_DOCUMENTS:
            if item["title"] in existing_titles:
                skipped += 1  # idempotent: zaten varsa atla
                continue
            doc = await documents.create(
                DocumentCreate(title=item["title"], content=item["content"], source="seed")
            )
            result = await ingestion.index_document(doc.id)
            chunks_total += result["chunks_created"] if result else 0
            created += 1

        print(
            f"{created} doküman oluşturuldu, {skipped} zaten vardı, "
            f"{chunks_total} chunk indexlendi"
        )


def main() -> None:
    """CLI giriş noktası."""
    parser = argparse.ArgumentParser(description="Support AI demo verisi üretir.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Demo kullanıcısının tüm dokümanlarını silip baştan oluştur.",
    )
    args = parser.parse_args()
    asyncio.run(seed(args.force))


if __name__ == "__main__":
    main()
