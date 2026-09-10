# Sohbet kalitesi — 10 Eylül 2026

## Yapılan değişiklik

Sohbet için kısa, ayrı sistem yönergesi ve ayrı üretim profili eklendi.
Kod araçlarının üretim ayarları değişmez. Sohbet sıcaklığı 0,35, çıktı sınırı 1024
token, istek zaman aşımı 90 saniyedir. Uzunluk sınırına takılan yanıt etiketlenir.
`qwen3` adlı modellerde sohbet düşünme modu kapatılır; diğer modellerde bu parametre
gönderilmez. Bu, daha derin muhakeme başarısı garantisi değil, gecikme tercihidir.
[Ollama düşünme kontrolü](https://docs.ollama.com/capabilities/thinking).

Hatırlama sorularında mevcut kullanıcı mesajlarını esas alan kısa tur yönergesi
kullanılır. Tavsiye istemeyen kullanıcıya çok sayıda soru döndürülürse en fazla
bir yeniden üretim yapılır. Başarısız üretim kullanıcının mesajını suçlamaz.
Model kendiliğinden değiştirilmez, indirme veya eğitim yapılmaz.

## Gerçek yanıtlar

| Deneme | Gözlenen sonuç |
| --- | --- |
| Önce, llama3.1: Defne yürüyüşe geliyor, Ali evde kalıyor | Yanlış yanıt: `Ali.` |
| Sonra, qwen3.5: aynı kişi sorusu | Doğru yanıt: `Defne.` |
| qwen3.5: salı toplantısı cuma olarak düzeltildi | `Cuma.` |
| qwen3.5: cuma matematik sınavını hatırlama, hazırlanmış geçmiş | `Cuma günü matematik sınavın varmış.` |
| qwen3.5: tavsiye istemeden içini dökme | `Tamam, dinliyorum. Ne oldu?` |
| qwen3.5: kedi Fındık → Tarçın; köpek Bulut; konu değişikliği sonrası | `Tarçın, Bulut.` |

Son altı hazırlanmış senaryoda qwen3.5:9b bütün otomatik kontrolleri geçti.
Model bellekteyken toplam üretim süresi 19,187 saniye; yanıt başına 1,775–4,347 saniye.
İlk yükleme ve başka modelden geçiş dahil önceki denemede ilk yanıt 24,432 saniyeydi.
Eski ayarlarla önceki turda 120 saniyelik zaman aşımı görülmüştü. Model sıcaklığı,
istem ve yükleme durumu birlikte değiştiğinden bu kontrollü bir hız karşılaştırması değildir.

**Çözülmemiş kalite sorunu:** Gerçek asistan yanıtlarıyla devam eden iki turluk sınav
sohbetinde model, kullanıcının söylediği `matematik` bilgisini iki denemede kaçırdı.
Ek kullanıcı-mesajı kopyası da bunu güvenilir biçimde çözmedi ve kaldırıldı.
Bu canlı test başarısız bırakıldı; beklentisi gevşetilmedi. Dört turluk isim düzeltmesi
testi geçti. Ayrıca gereksiz takip soruları, kalıp ifadeler ve dil hataları görüldü.

Llama3.1 karşılaştırmada hâlâ kişi karıştırdı ve bir denemede verilmemiş İstanbul
doğum yeri/profil kaydı uydurdu. İstem değişikliğinin her modelde kaliteyi yükselttiği
iddia edilemez. Bir kelimenin yanıtta bulunması da doğru cevap demek değildir:
`Cuma matematik sınavı bilgisine ulaşamadım` gibi olumsuz yanıtlar ayrıca denetlenir.
Türkçe büyük `İ` nedeniyle kaçan kontrol düzeltildi.

## Yeniden deneme

Son kod doğrulaması: 916 test keşfedildi; 894 geçti, 22 isteğe bağlı test atlandı.
Canlı model denemesi bu sayıdan ayrıdır: konu değişikliği testi geçti, iki turluk
sınav hatırlama testi başarısız oldu. `git diff --check` geçti.

PowerShell'de, proje kökünde:

```powershell
$env:BORU_CHAT_MODEL="qwen3.5:9b"
python main.py
```

Bu ayar kodlama modelini değiştirmez. Mevcut modeli kullanmak için ayarı boş bırakın.
Altı senaryoluk karşılaştırma uygulama sohbetine değil PowerShell'e yazılır:

```powershell
python -B -m boru.conversation_eval --models llama3.1:latest,qwen3.5:9b --label comparison
$env:BORU_LIVE_CHAT="1"
$env:BORU_LIVE_CHAT_MODEL="qwen3.5:9b"
python -B -m unittest tests.test_conversation_live
```

Raporlar `data/conversation_evals/` altında benzersiz JSON dosyalarına yazılır ve Git'e
eklenmez. Yalnızca kurmaca diyaloglar kullanılır; kullanıcı profili, özel dosya veya web
araştırması bu değerlendirmeye dahil değildir. İlk altı senaryo hazırlanmış geçmiş
kullanır; canlı unittest senaryoları modelin gerçek önceki yanıtlarıyla devam eder.
Raporlarda istem, cevap, süre, kontroller ve inceleme ölçütü saklanır. `checks_passed`
yalnızca otomatik koşulların geçtiğini söyler; doğal dilin anlamsal doğruluğu veya
empati puanı değildir. İnsan değerlendirmesi yapılmış gibi işaretlenmez.

Ham raporlar:
- İlk durum: `data/conversation_evals/b0a51b9fb53e4b04a3e203ad11820773.json`
- İki model: `data/conversation_evals/91691bb9a8714dbaa3b4d8f666614e78.json`
- Kısa hatırlama yönergesi: `data/conversation_evals/059bc5e736444e4d813555df65c36837.json`

Eski raporlardaki kontrol sonuçları o anki denetleyici sürümünü yansıtır; yukarıdaki
karşılaştırma yanıtların kendisine dayanır. Dar örneklerle ayarlanan bu sistem için
genel sohbet başarısı, bağımsız/kör değerlendirme veya kusursuzluk iddia edilmez.
